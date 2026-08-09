from datetime import UTC, datetime

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
    authenticated_at = datetime.now(UTC)
    access_token = create_access_token(
        {
            "sub": user.username,
            "amr": authentication_methods,
            "auth_time": int(authenticated_at.timestamp()),
        }
    )
    refresh_token, expires_at = create_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
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
