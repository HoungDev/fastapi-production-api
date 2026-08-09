import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.config import settings


def hash_refresh_token(
    token: str,
) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_refresh_token() -> tuple[str, datetime]:
    token = secrets.token_urlsafe(64)

    expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    return token, expires_at


def create_refresh_token_family_id() -> str:
    return str(uuid4())


def normalize_device_name(
    device_name: str | None,
    user_agent: str | None,
) -> str:
    candidate = device_name or user_agent or "Unknown device"
    printable = "".join(
        character if character.isprintable() else " " for character in candidate
    )
    normalized = " ".join(printable.split()).strip()
    return (normalized or "Unknown device")[:100]
