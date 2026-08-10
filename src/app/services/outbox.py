import hashlib
import json
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.tracing import capture_trace_context
from app.models.outbox_message import OutboxMessage
from app.services.account_action_tokens import as_utc, utc_now

EMAIL_VERIFICATION_MESSAGE = "email_verification.v1"
PASSWORD_RESET_MESSAGE = "password_reset.v1"
SUPPORTED_MESSAGE_TYPES = frozenset(
    {EMAIL_VERIFICATION_MESSAGE, PASSWORD_RESET_MESSAGE}
)


def _fernet() -> Fernet:
    return Fernet(settings.OUTBOX_ENCRYPTION_KEY.get_secret_value().encode("ascii"))


def outbox_idempotency_key(message_type: str, token_hash: str) -> str:
    value = f"fastapi-production-api:outbox:v1:{message_type}:{token_hash}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def enqueue_email_delivery(
    db: Session,
    *,
    message_type: str,
    recipient: str,
    token: str,
    token_hash: str,
    action_url: str,
    expires_at: datetime,
) -> OutboxMessage:
    if message_type not in SUPPORTED_MESSAGE_TYPES:
        raise ValueError("Unsupported outbox message type")

    payload = json.dumps(
        {
            "action_url": action_url,
            "recipient": recipient,
            "token": token,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    now = utc_now()
    traceparent, tracestate = capture_trace_context()

    message = OutboxMessage(
        message_type=message_type,
        idempotency_key=outbox_idempotency_key(message_type, token_hash),
        encryption_version=1,
        payload_encrypted=_fernet().encrypt(payload),
        status="pending",
        attempt_count=0,
        available_at=now,
        payload_expires_at=as_utc(expires_at),
        traceparent=traceparent,
        tracestate=tracestate,
        created_at=now,
        updated_at=now,
    )

    db.add(message)
    return message


def decrypt_email_payload(message: OutboxMessage) -> dict[str, str]:
    if message.encryption_version != 1 or message.payload_encrypted is None:
        raise ValueError("Unsupported or missing encrypted payload")

    try:
        decoded = _fernet().decrypt(message.payload_encrypted)
        payload = json.loads(decoded)
    except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid encrypted outbox payload") from exc

    if not isinstance(payload, dict):
        raise ValueError("Invalid outbox payload shape")

    expected = {"action_url", "recipient", "token"}

    if set(payload) != expected or not all(
        isinstance(payload[field], str) and payload[field] for field in expected
    ):
        raise ValueError("Invalid outbox payload fields")

    return payload
