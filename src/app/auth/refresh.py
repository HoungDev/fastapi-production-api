from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.auth.jwt import create_access_token
from app.auth.refresh_token import (
    create_refresh_token,
    hash_refresh_token,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User

ROTATION_REASON = "rotated"
REPLAY_REASON = "reuse_detected"
LOGOUT_REASON = "logout"


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _revoke_family(
    family_id: str,
    db: Session,
    *,
    reason: str,
    revoked_at: datetime,
) -> None:
    db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked.is_(False),
        )
        .values(
            revoked=True,
            revoked_at=revoked_at,
            revocation_reason=reason,
        )
    )


def refresh_access_token(
    refresh_token: str,
    db: Session,
):
    hashed_token = hash_refresh_token(refresh_token)

    stored_token = (
        db.query(RefreshToken)
        .filter(RefreshToken.token == hashed_token)
        .with_for_update()
        .first()
    )

    if not stored_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    if stored_token.revoked:
        try:
            _revoke_family(
                stored_token.family_id,
                db,
                reason=REPLAY_REASON,
                revoked_at=datetime.now(UTC),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    if _as_utc(stored_token.expires_at) < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    user = db.query(User).filter(User.id == stored_token.user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    new_refresh_token, expires_at = create_refresh_token()

    new_db_refresh_token = RefreshToken(
        user_id=user.id,
        family_id=stored_token.family_id,
        token=hash_refresh_token(new_refresh_token),
        expires_at=expires_at,
        device_name=stored_token.device_name,
    )

    try:
        now = datetime.now(UTC)
        stored_token.revoked = True
        stored_token.revoked_at = now
        stored_token.revocation_reason = ROTATION_REASON
        stored_token.last_used_at = now

        db.add(new_db_refresh_token)
        db.commit()

    except Exception:
        db.rollback()
        raise

    access_token = create_access_token(
        {
            "sub": user.username,
            "amr": ["refresh"],
        }
    )

    return (
        access_token,
        new_refresh_token,
    )


def revoke_refresh_token(
    refresh_token: str,
    db: Session,
):
    hashed_token = hash_refresh_token(refresh_token)

    stored_token = (
        db.query(RefreshToken)
        .filter(RefreshToken.token == hashed_token)
        .with_for_update()
        .first()
    )

    if not stored_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    try:
        _revoke_family(
            stored_token.family_id,
            db,
            reason=LOGOUT_REASON,
            revoked_at=datetime.now(UTC),
        )
        db.commit()

    except Exception:
        db.rollback()
        raise

    return True
