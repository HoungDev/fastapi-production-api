from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.core.config import settings
from app.models.account_action_token import AccountActionToken
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.account_action_tokens import (
    as_utc,
    generate_account_action_token,
    hash_account_action_token,
    utc_now,
)

PASSWORD_RESET_PURPOSE = "password_reset"
INVALID_TOKEN_DETAIL = "Invalid or expired password reset token"


def issue_password_reset_token(
    email: str,
    db: Session,
) -> tuple[str, str] | None:
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active or user.email_verified_at is None:
        return None

    now = utc_now()
    raw_token = generate_account_action_token()
    token = AccountActionToken(
        user_id=user.id,
        purpose=PASSWORD_RESET_PURPOSE,
        token_hash=hash_account_action_token(raw_token),
        target=email,
        expires_at=now
        + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
    )

    try:
        db.execute(
            update(AccountActionToken)
            .where(
                AccountActionToken.user_id == user.id,
                AccountActionToken.purpose == PASSWORD_RESET_PURPOSE,
                AccountActionToken.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        db.add(token)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return email, raw_token


def confirm_password_reset(
    token: str,
    new_password: str,
    db: Session,
) -> None:
    token_hash = hash_account_action_token(token)
    stored_token = (
        db.query(AccountActionToken)
        .filter(
            AccountActionToken.token_hash == token_hash,
            AccountActionToken.purpose == PASSWORD_RESET_PURPOSE,
        )
        .with_for_update()
        .first()
    )
    now = utc_now()

    if (
        stored_token is None
        or stored_token.consumed_at is not None
        or as_utc(stored_token.expires_at) <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=INVALID_TOKEN_DETAIL,
        )

    user = (
        db.query(User).filter(User.id == stored_token.user_id).with_for_update().first()
    )
    if (
        user is None
        or not user.is_active
        or user.email_verified_at is None
        or user.email != stored_token.target
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=INVALID_TOKEN_DETAIL,
        )

    new_password_hash = hash_password(new_password)

    try:
        user.password = new_password_hash
        user.password_login_enabled = True
        db.execute(
            update(AccountActionToken)
            .where(
                AccountActionToken.user_id == user.id,
                AccountActionToken.purpose == PASSWORD_RESET_PURPOSE,
                AccountActionToken.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user.id,
                RefreshToken.revoked.is_(False),
            )
            .values(
                revoked=True,
                revoked_at=now,
                revocation_reason="password_reset",
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
