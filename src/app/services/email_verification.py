from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.account_action_token import AccountActionToken
from app.models.user import User
from app.services.account_action_tokens import (
    as_utc,
    generate_account_action_token,
    hash_account_action_token,
    utc_now,
)
from app.services.outbox import EMAIL_VERIFICATION_MESSAGE, enqueue_email_delivery

EMAIL_VERIFICATION_PURPOSE = "email_verification"
INVALID_TOKEN_DETAIL = "Invalid or expired verification token"


def issue_email_verification_token(
    email: str,
    db: Session,
) -> tuple[str, str] | None:
    user = db.query(User).filter(User.email == email).first()
    if user is None or user.email_verified_at is not None:
        return None

    now = utc_now()
    raw_token = generate_account_action_token()
    token = AccountActionToken(
        user_id=user.id,
        purpose=EMAIL_VERIFICATION_PURPOSE,
        token_hash=hash_account_action_token(raw_token),
        target=email,
        expires_at=now
        + timedelta(minutes=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES),
    )

    try:
        db.execute(
            update(AccountActionToken)
            .where(
                AccountActionToken.user_id == user.id,
                AccountActionToken.purpose == EMAIL_VERIFICATION_PURPOSE,
                AccountActionToken.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        db.add(token)
        if settings.EMAIL_DELIVERY_MODE == "outbox":
            enqueue_email_delivery(
                db,
                message_type=EMAIL_VERIFICATION_MESSAGE,
                recipient=email,
                token=raw_token,
                token_hash=token.token_hash,
                action_url=settings.EMAIL_VERIFICATION_URL,
                expires_at=token.expires_at,
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return email, raw_token


def confirm_email_verification(token: str, db: Session) -> None:
    token_hash = hash_account_action_token(token)
    stored_token = (
        db.query(AccountActionToken)
        .filter(
            AccountActionToken.token_hash == token_hash,
            AccountActionToken.purpose == EMAIL_VERIFICATION_PURPOSE,
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

    user = db.query(User).filter(User.id == stored_token.user_id).first()
    if user is None or user.email != stored_token.target:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=INVALID_TOKEN_DETAIL,
        )

    try:
        stored_token.consumed_at = now
        user.email_verified_at = now
        db.commit()
    except Exception:
        db.rollback()
        raise
