from datetime import datetime, UTC

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.auth.jwt import create_access_token
from app.auth.refresh_token import hash_refresh_token
from app.models.refresh_token import RefreshToken
from app.models.user import User


def refresh_access_token(
    refresh_token: str,
    db: Session,
):
    hashed_token = hash_refresh_token(
        refresh_token
    )

    stored_token = db.query(RefreshToken).filter(
        RefreshToken.token == hashed_token
    ).first()

    if not stored_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    if stored_token.revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revoked",
        )

    if stored_token.expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    user = db.query(User).filter(
        User.id == stored_token.user_id
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    access_token = create_access_token(
        {
            "sub": user.username,
        }
    )

    return access_token


def revoke_refresh_token(
    refresh_token: str,
    db: Session,
):
    hashed_token = hash_refresh_token(
        refresh_token
    )

    stored_token = db.query(RefreshToken).filter(
        RefreshToken.token == hashed_token
    ).first()

    if not stored_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    stored_token.revoked = True

    db.commit()

    return True