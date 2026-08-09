import hashlib
import secrets
from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def generate_account_action_token() -> str:
    return secrets.token_urlsafe(32)


def hash_account_action_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
