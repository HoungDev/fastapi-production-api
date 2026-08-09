import base64
import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta
from hmac import compare_digest
from typing import Literal
from urllib.parse import urlencode

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import delete, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.core.config import settings
from app.models.external_identity import ExternalIdentity
from app.models.oidc_transaction import OIDCTransaction
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.mfa import MFAChallengeResponse
from app.schemas.oidc import OIDCLinkResponse
from app.schemas.token import Token
from app.services.account_action_tokens import as_utc, utc_now
from app.services.mfa import prepare_mfa_login_challenge
from app.services.oidc_provider import OIDCProviderClient, OIDCProviderError
from app.services.session_issuance import prepare_session_tokens

INVALID_TRANSACTION = "Invalid or expired OIDC transaction"
BROWSER_COOKIE_NAME = "oidc_browser_binding"


@dataclass(frozen=True)
class OIDCAuthorizationStart:
    authorization_url: str
    browser_binding: str
    expires_in: int


@dataclass(frozen=True)
class OIDCCallbackResult:
    kind: Literal["tokens", "mfa", "linked"]
    response: Token | MFAChallengeResponse | OIDCLinkResponse


def _require_available() -> Fernet:
    if not settings.OIDC_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC is not available",
        )
    try:
        return Fernet(
            settings.OIDC_TRANSACTION_ENCRYPTION_KEY.get_secret_value().encode("ascii")
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC is not available",
        ) from exc


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _decrypt_verifier(encrypted: str, fernet: Fernet) -> str:
    try:
        return fernet.decrypt(encrypted.encode("ascii")).decode("ascii")
    except (InvalidToken, UnicodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC is not available",
        ) from exc


def begin_oidc_authorization(
    db: Session,
    provider: OIDCProviderClient,
    *,
    intent: Literal["login", "link"],
    device_name: str,
    user_id: int | None = None,
) -> OIDCAuthorizationStart:
    fernet = _require_available()
    if (intent == "link") != (user_id is not None):
        raise ValueError("OIDC link transactions must be bound to a user")
    try:
        metadata = provider.discover()
    except OIDCProviderError as exc:
        raise HTTPException(
            status_code=502, detail="OIDC provider unavailable"
        ) from exc

    state = secrets.token_urlsafe(32)
    browser_binding = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    now = utc_now()
    expires_at = now + timedelta(minutes=settings.OIDC_TRANSACTION_EXPIRE_MINUTES)
    transaction = OIDCTransaction(
        state_hash=_hash_secret(state),
        browser_binding_hash=_hash_secret(browser_binding),
        nonce_hash=_hash_secret(nonce),
        code_verifier_encrypted=fernet.encrypt(verifier.encode("ascii")).decode(
            "ascii"
        ),
        intent=intent,
        user_id=user_id,
        issuer=metadata.issuer,
        redirect_uri=settings.OIDC_REDIRECT_URI,
        device_name=device_name,
        expires_at=expires_at,
    )
    try:
        db.add(transaction)
        db.commit()
    except Exception:
        db.rollback()
        raise

    parameters = urlencode(
        {
            "response_type": "code",
            "client_id": settings.OIDC_CLIENT_ID,
            "redirect_uri": settings.OIDC_REDIRECT_URI,
            "scope": settings.OIDC_SCOPES,
            "state": state,
            "nonce": nonce,
            "code_challenge": _code_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    separator = "&" if "?" in metadata.authorization_endpoint else "?"
    return OIDCAuthorizationStart(
        authorization_url=f"{metadata.authorization_endpoint}{separator}{parameters}",
        browser_binding=browser_binding,
        expires_in=settings.OIDC_TRANSACTION_EXPIRE_MINUTES * 60,
    )


def _normalize_verified_email(claims: dict) -> str | None:
    email = claims.get("email")
    if claims.get("email_verified") is not True or not isinstance(email, str):
        return None
    try:
        validated = TypeAdapter(EmailStr).validate_python(email)
    except ValidationError:
        return None
    return str(validated).strip().casefold()


def _new_username(email: str, issuer: str, subject: str, db: Session) -> str:
    local = re.sub(r"[^a-z0-9_.-]", "-", email.split("@", 1)[0].casefold())
    local = local.strip("-._")[:30] or "oidc-user"
    digest = hashlib.sha256(f"{issuer}\0{subject}".encode()).hexdigest()[:12]
    base = f"{local}-{digest}"[:50]
    candidate = base
    suffix = 1
    while db.query(User.id).filter(User.username == candidate).first() is not None:
        suffix_text = f"-{suffix}"
        candidate = f"{base[: 50 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate


def _revoke_user_sessions(user_id: int, db: Session, reason: str) -> None:
    now = utc_now()
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .values(revoked=True, revoked_at=now, revocation_reason=reason)
    )


def _identity_for_login(
    issuer: str,
    subject: str,
    claims: dict,
    db: Session,
) -> tuple[ExternalIdentity, User]:
    identity = (
        db.query(ExternalIdentity)
        .filter(
            ExternalIdentity.issuer == issuer,
            ExternalIdentity.subject == subject,
        )
        .with_for_update()
        .first()
    )
    if identity is not None:
        user = (
            db.query(User).filter(User.id == identity.user_id).with_for_update().first()
        )
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="OIDC login is not available")
        return identity, user

    email = _normalize_verified_email(claims)
    if email is None:
        raise HTTPException(
            status_code=403,
            detail="Verified provider email is required for account creation",
        )
    existing_user = (
        db.query(User)
        .filter(func.lower(func.trim(User.email)) == email)
        .with_for_update()
        .first()
    )
    if existing_user is not None:
        raise HTTPException(
            status_code=409,
            detail="Sign in locally and link this external identity explicitly",
        )

    now = utc_now()
    user = User(
        username=_new_username(email, issuer, subject, db),
        email=email,
        email_verified_at=now,
        password=hash_password(secrets.token_urlsafe(48)),
        password_login_enabled=False,
    )
    db.add(user)
    db.flush()
    identity = ExternalIdentity(
        user_id=user.id,
        issuer=issuer,
        subject=subject,
        email=email,
        last_login_at=now,
    )
    db.add(identity)
    return identity, user


def _identity_for_link(
    user_id: int,
    issuer: str,
    subject: str,
    claims: dict,
    db: Session,
) -> ExternalIdentity:
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail=INVALID_TRANSACTION)
    existing_subject = (
        db.query(ExternalIdentity)
        .filter(
            ExternalIdentity.issuer == issuer,
            ExternalIdentity.subject == subject,
        )
        .with_for_update()
        .first()
    )
    if existing_subject is not None:
        if existing_subject.user_id != user_id:
            raise HTTPException(
                status_code=409,
                detail="External identity is already linked to another account",
            )
        return existing_subject
    existing_provider = (
        db.query(ExternalIdentity)
        .filter(
            ExternalIdentity.user_id == user_id,
            ExternalIdentity.issuer == issuer,
        )
        .with_for_update()
        .first()
    )
    if existing_provider is not None:
        raise HTTPException(
            status_code=409,
            detail="This account already has an identity for the provider",
        )
    identity = ExternalIdentity(
        user_id=user_id,
        issuer=issuer,
        subject=subject,
        email=_normalize_verified_email(claims),
    )
    db.add(identity)
    db.flush()
    _revoke_user_sessions(user_id, db, "external_identity_linked")
    return identity


def complete_oidc_authorization(
    state: str,
    code: str,
    browser_binding: str | None,
    db: Session,
    provider: OIDCProviderClient,
) -> OIDCCallbackResult:
    fernet = _require_available()
    if not state or not code or not browser_binding:
        raise HTTPException(status_code=400, detail=INVALID_TRANSACTION)
    now = utc_now()
    transaction = (
        db.query(OIDCTransaction)
        .filter(OIDCTransaction.state_hash == _hash_secret(state))
        .with_for_update()
        .first()
    )
    if (
        transaction is None
        or transaction.consumed_at is not None
        or as_utc(transaction.expires_at) <= now
        or transaction.issuer != settings.OIDC_ISSUER.rstrip("/")
        or transaction.redirect_uri != settings.OIDC_REDIRECT_URI
        or not compare_digest(
            transaction.browser_binding_hash,
            _hash_secret(browser_binding),
        )
    ):
        raise HTTPException(status_code=400, detail=INVALID_TRANSACTION)

    try:
        metadata = provider.discover()
        verifier = _decrypt_verifier(transaction.code_verifier_encrypted, fernet)
        id_token = provider.exchange_code(
            metadata,
            code=code,
            code_verifier=verifier,
            redirect_uri=transaction.redirect_uri,
        )
        claims = provider.validate_id_token(metadata, id_token)
    except OIDCProviderError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=INVALID_TRANSACTION) from exc

    subject = claims.get("sub")
    nonce = claims.get("nonce")
    if (
        not isinstance(subject, str)
        or not subject
        or len(subject) > 255
        or not isinstance(nonce, str)
        or not compare_digest(transaction.nonce_hash, _hash_secret(nonce))
    ):
        db.rollback()
        raise HTTPException(status_code=400, detail=INVALID_TRANSACTION)

    try:
        transaction.consumed_at = now
        if transaction.intent == "link":
            if transaction.user_id is None:
                raise HTTPException(status_code=400, detail=INVALID_TRANSACTION)
            identity = _identity_for_link(
                transaction.user_id,
                metadata.issuer,
                subject,
                claims,
                db,
            )
            response = OIDCLinkResponse(identity=identity)
            result = OIDCCallbackResult(kind="linked", response=response)
        elif transaction.intent == "login":
            identity, user = _identity_for_login(
                metadata.issuer,
                subject,
                claims,
                db,
            )
            identity.email = _normalize_verified_email(claims) or identity.email
            identity.last_login_at = now
            if user.mfa_enabled_at is not None:
                challenge = prepare_mfa_login_challenge(
                    user,
                    transaction.device_name,
                    db,
                    primary_method="oidc",
                )
                result = OIDCCallbackResult(kind="mfa", response=challenge)
            else:
                tokens = prepare_session_tokens(
                    user,
                    transaction.device_name,
                    db,
                    authentication_methods=["oidc"],
                )
                result = OIDCCallbackResult(kind="tokens", response=tokens)
        else:
            raise HTTPException(status_code=400, detail=INVALID_TRANSACTION)
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="External identity could not be linked"
        ) from exc
    except Exception:
        db.rollback()
        raise


def list_external_identities(user_id: int, db: Session) -> list[ExternalIdentity]:
    return (
        db.query(ExternalIdentity)
        .filter(ExternalIdentity.user_id == user_id)
        .order_by(ExternalIdentity.created_at, ExternalIdentity.id)
        .all()
    )


def unlink_external_identity(identity_id: int, user_id: int, db: Session) -> None:
    identity = (
        db.query(ExternalIdentity)
        .filter(
            ExternalIdentity.id == identity_id,
            ExternalIdentity.user_id == user_id,
        )
        .with_for_update()
        .first()
    )
    if identity is None:
        return
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    identity_count = (
        db.query(func.count(ExternalIdentity.id))
        .filter(ExternalIdentity.user_id == user_id)
        .scalar()
        or 0
    )
    if user is None or (not user.password_login_enabled and identity_count <= 1):
        raise HTTPException(
            status_code=409,
            detail="Cannot unlink the account's only sign-in method",
        )
    try:
        db.execute(delete(ExternalIdentity).where(ExternalIdentity.id == identity.id))
        _revoke_user_sessions(user_id, db, "external_identity_unlinked")
        db.commit()
    except Exception:
        db.rollback()
        raise
