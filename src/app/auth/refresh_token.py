import secrets

from datetime import datetime, timedelta, UTC

from app.core.config import settings


def create_refresh_token() -> tuple[str, datetime]:
    token = secrets.token_urlsafe(64)

    expires_at = (
        datetime.now(UTC)
        + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
    )

    return token, expires_at