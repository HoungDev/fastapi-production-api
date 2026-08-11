from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.auth.jwt import create_access_token
from app.auth.refresh_token import (
    create_refresh_token,
    create_refresh_token_family_id,
    hash_refresh_token,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.token import Token


def prepare_session_tokens(
    user: User,
    device_name: str,
    db: Session,
    *,
    authentication_methods: list[str],
) -> Token:
    # SessionLocal disables autoflush. Preserve pending security state, such as
    # an accepted MFA counter, before populate_existing reloads the locked row.
    db.flush()
    active_user = (
        db.query(User)
        .filter(User.id == user.id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if active_user is None or not active_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is not available",
        )

    authenticated_at = datetime.now(UTC)
    access_token = create_access_token(
        {
            "sub": active_user.username,
            "amr": authentication_methods,
            "auth_time": int(authenticated_at.timestamp()),
        }
    )
    refresh_token, expires_at = create_refresh_token()
    db.add(
        RefreshToken(
            user_id=active_user.id,
            family_id=create_refresh_token_family_id(),
            token=hash_refresh_token(refresh_token),
            expires_at=expires_at,
            device_name=device_name,
        )
    )
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )
