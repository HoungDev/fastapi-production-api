import hashlib
import secrets
from datetime import datetime, timedelta

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from sqlalchemy import delete, func, update
from sqlalchemy.orm import Session

from app.auth.security import verify_password
from app.core.config import settings
from app.models.account_action_token import AccountActionToken
from app.models.mfa_recovery_code import MFARecoveryCode
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.mfa import (
    MFAChallengeResponse,
    MFAEnrollmentResponse,
    MFARecoveryCodesResponse,
    MFAStatusResponse,
)
from app.schemas.token import Token
from app.services.account_action_tokens import (
    as_utc,
    generate_account_action_token,
    hash_account_action_token,
    utc_now,
)
from app.services.session_issuance import prepare_session_tokens

MFA_LOGIN_PURPOSE = "mfa_login"
OIDC_MFA_LOGIN_PURPOSE = "mfa_login_oidc"
INVALID_FACTOR_DETAIL = "Invalid MFA credential"
INVALID_CHALLENGE_DETAIL = "Invalid or expired MFA challenge"


def _require_available() -> Fernet:
    if not settings.MFA_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA is not available",
        )
    try:
        return Fernet(settings.MFA_ENCRYPTION_KEY.get_secret_value().encode("ascii"))
    except (TypeError, ValueError, UnicodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA is not available",
        ) from exc


def _encrypt_secret(secret: str) -> str:
    return _require_available().encrypt(secret.encode("ascii")).decode("ascii")


def _decrypt_secret(encrypted_secret: str) -> str:
    try:
        return (
            _require_available()
            .decrypt(encrypted_secret.encode("ascii"))
            .decode("ascii")
        )
    except (InvalidToken, UnicodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA is not available",
        ) from exc


def _lock_user(user_id: int, db: Session) -> User:
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail=INVALID_FACTOR_DETAIL)
    return user


def _verify_current_password(user: User, password: str) -> None:
    if not verify_password(password, user.password):
        raise HTTPException(status_code=401, detail=INVALID_FACTOR_DETAIL)


def _matching_totp_counter(user: User, code: str, now: datetime) -> int | None:
    if not code.isdigit() or len(code) != 6 or not user.mfa_secret_encrypted:
        return None
    secret = _decrypt_secret(user.mfa_secret_encrypted)
    totp = pyotp.TOTP(secret, interval=30, digits=6)
    current_counter = int(now.timestamp()) // 30
    for offset in (-1, 0, 1):
        counter = current_counter + offset
        if pyotp.utils.strings_equal(totp.generate_otp(counter), code):
            if user.mfa_last_counter is not None and counter <= user.mfa_last_counter:
                return None
            return counter
    return None


def _normalize_recovery_code(code: str) -> str:
    return code.replace("-", "").strip().upper()


def _hash_recovery_code(code: str) -> str:
    return hashlib.sha256(_normalize_recovery_code(code).encode("ascii")).hexdigest()


def _new_recovery_codes() -> list[str]:
    codes = []
    for _ in range(settings.MFA_RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(10).upper()
        codes.append("-".join(raw[index : index + 4] for index in range(0, 20, 4)))
    return codes


def _replace_recovery_codes(user_id: int, db: Session) -> list[str]:
    codes = _new_recovery_codes()
    db.execute(delete(MFARecoveryCode).where(MFARecoveryCode.user_id == user_id))
    for code in codes:
        db.add(MFARecoveryCode(user_id=user_id, code_hash=_hash_recovery_code(code)))
    return codes


def _consume_recovery_code(user_id: int, code: str, db: Session, now: datetime) -> bool:
    try:
        code_hash = _hash_recovery_code(code)
    except UnicodeEncodeError:
        return False
    recovery = (
        db.query(MFARecoveryCode)
        .filter(
            MFARecoveryCode.user_id == user_id,
            MFARecoveryCode.code_hash == code_hash,
            MFARecoveryCode.used_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    if recovery is None:
        return False
    recovery.used_at = now
    return True


def _revoke_sessions(user_id: int, db: Session, now: datetime, reason: str) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .values(revoked=True, revoked_at=now, revocation_reason=reason)
    )


def get_mfa_status(user_id: int, db: Session) -> MFAStatusResponse:
    user = db.query(User).filter(User.id == user_id).first()
    remaining = 0
    if user is not None and user.mfa_enabled_at is not None:
        remaining = (
            db.query(func.count(MFARecoveryCode.id))
            .filter(
                MFARecoveryCode.user_id == user_id,
                MFARecoveryCode.used_at.is_(None),
            )
            .scalar()
            or 0
        )
    return MFAStatusResponse(
        enabled=bool(user and user.mfa_enabled_at),
        recovery_codes_remaining=remaining,
    )


def begin_totp_enrollment(
    user_id: int,
    password: str,
    db: Session,
) -> MFAEnrollmentResponse:
    _require_available()
    user = _lock_user(user_id, db)
    _verify_current_password(user, password)
    if user.mfa_enabled_at is not None:
        raise HTTPException(status_code=409, detail="MFA is already enabled")

    now = utc_now()
    secret = pyotp.random_base32()
    try:
        user.mfa_secret_encrypted = _encrypt_secret(secret)
        user.mfa_enrollment_created_at = now
        user.mfa_last_counter = None
        db.execute(delete(MFARecoveryCode).where(MFARecoveryCode.user_id == user.id))
        db.commit()
    except Exception:
        db.rollback()
        raise

    return MFAEnrollmentResponse(
        secret=secret,
        provisioning_uri=pyotp.TOTP(secret).provisioning_uri(
            name=user.email or user.username,
            issuer_name=settings.MFA_ISSUER,
        ),
        expires_at=now + timedelta(minutes=settings.MFA_ENROLLMENT_EXPIRE_MINUTES),
    )


def confirm_totp_enrollment(
    user_id: int,
    code: str,
    db: Session,
) -> MFARecoveryCodesResponse:
    user = _lock_user(user_id, db)
    now = utc_now()
    if (
        user.mfa_enabled_at is not None
        or user.mfa_enrollment_created_at is None
        or as_utc(user.mfa_enrollment_created_at)
        + timedelta(minutes=settings.MFA_ENROLLMENT_EXPIRE_MINUTES)
        <= now
    ):
        raise HTTPException(status_code=400, detail=INVALID_FACTOR_DETAIL)

    counter = _matching_totp_counter(user, code, now)
    if counter is None:
        raise HTTPException(status_code=400, detail=INVALID_FACTOR_DETAIL)

    try:
        codes = _replace_recovery_codes(user.id, db)
        user.mfa_enabled_at = now
        user.mfa_enrollment_created_at = None
        user.mfa_last_counter = counter
        db.commit()
    except Exception:
        db.rollback()
        raise
    return MFARecoveryCodesResponse(recovery_codes=codes)


def regenerate_recovery_codes(
    user_id: int,
    password: str,
    code: str,
    db: Session,
) -> MFARecoveryCodesResponse:
    user = _lock_user(user_id, db)
    _verify_current_password(user, password)
    if user.mfa_enabled_at is None:
        raise HTTPException(status_code=400, detail=INVALID_FACTOR_DETAIL)
    now = utc_now()
    counter = _matching_totp_counter(user, code, now)
    if counter is None:
        raise HTTPException(status_code=400, detail=INVALID_FACTOR_DETAIL)
    try:
        codes = _replace_recovery_codes(user.id, db)
        user.mfa_last_counter = counter
        _revoke_sessions(user.id, db, now, "mfa_recovery_regenerated")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return MFARecoveryCodesResponse(recovery_codes=codes)


def disable_mfa(
    user_id: int,
    password: str,
    code: str,
    db: Session,
) -> None:
    user = _lock_user(user_id, db)
    _verify_current_password(user, password)
    if user.mfa_enabled_at is None:
        raise HTTPException(status_code=400, detail=INVALID_FACTOR_DETAIL)
    now = utc_now()
    counter = _matching_totp_counter(user, code, now)
    valid = counter is not None
    if not valid:
        valid = _consume_recovery_code(user.id, code, db, now)
    if not valid:
        raise HTTPException(status_code=400, detail=INVALID_FACTOR_DETAIL)
    try:
        user.mfa_secret_encrypted = None
        user.mfa_enrollment_created_at = None
        user.mfa_enabled_at = None
        user.mfa_last_counter = None
        db.execute(delete(MFARecoveryCode).where(MFARecoveryCode.user_id == user.id))
        _revoke_sessions(user.id, db, now, "mfa_disabled")
        db.commit()
    except Exception:
        db.rollback()
        raise


def issue_mfa_login_challenge(
    user: User,
    device_name: str,
    db: Session,
) -> MFAChallengeResponse:
    try:
        response = prepare_mfa_login_challenge(
            user,
            device_name,
            db,
            primary_method="pwd",
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return response


def prepare_mfa_login_challenge(
    user: User,
    device_name: str,
    db: Session,
    *,
    primary_method: str,
) -> MFAChallengeResponse:
    _require_available()
    if primary_method not in {"pwd", "oidc"}:
        raise ValueError("Unsupported primary authentication method")
    now = utc_now()
    raw_token = generate_account_action_token()
    purpose = OIDC_MFA_LOGIN_PURPOSE if primary_method == "oidc" else MFA_LOGIN_PURPOSE
    db.execute(
        update(AccountActionToken)
        .where(
            AccountActionToken.user_id == user.id,
            AccountActionToken.purpose.in_((MFA_LOGIN_PURPOSE, OIDC_MFA_LOGIN_PURPOSE)),
            AccountActionToken.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    db.add(
        AccountActionToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_account_action_token(raw_token),
            target=device_name,
            expires_at=now + timedelta(minutes=settings.MFA_CHALLENGE_EXPIRE_MINUTES),
        )
    )
    return MFAChallengeResponse(
        challenge_token=raw_token,
        expires_in=settings.MFA_CHALLENGE_EXPIRE_MINUTES * 60,
    )


def verify_mfa_login_challenge(
    challenge_token: str,
    code: str,
    db: Session,
) -> Token:
    _require_available()
    now = utc_now()
    challenge = (
        db.query(AccountActionToken)
        .filter(
            AccountActionToken.token_hash == hash_account_action_token(challenge_token),
            AccountActionToken.purpose.in_((MFA_LOGIN_PURPOSE, OIDC_MFA_LOGIN_PURPOSE)),
        )
        .with_for_update()
        .first()
    )
    if (
        challenge is None
        or challenge.consumed_at is not None
        or as_utc(challenge.expires_at) <= now
    ):
        raise HTTPException(status_code=400, detail=INVALID_CHALLENGE_DETAIL)

    user = _lock_user(challenge.user_id, db)
    if user.mfa_enabled_at is None:
        raise HTTPException(status_code=400, detail=INVALID_CHALLENGE_DETAIL)

    counter = _matching_totp_counter(user, code, now)
    authentication_method = "otp"
    if counter is None:
        if not _consume_recovery_code(user.id, code, db, now):
            raise HTTPException(status_code=400, detail=INVALID_FACTOR_DETAIL)
        authentication_method = "recovery"
        _revoke_sessions(user.id, db, now, "mfa_recovery_used")

    try:
        challenge.consumed_at = now
        if counter is not None:
            user.mfa_last_counter = counter
        primary_method = (
            "oidc" if challenge.purpose == OIDC_MFA_LOGIN_PURPOSE else "pwd"
        )
        tokens = prepare_session_tokens(
            user,
            challenge.target,
            db,
            authentication_methods=[primary_method, authentication_method],
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return tokens
