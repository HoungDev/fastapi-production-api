import hashlib
import logging
import smtplib
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.metrics import (
    OUTBOX_DELIVERY_DURATION_SECONDS,
    OUTBOX_FAILURES_TOTAL,
    OUTBOX_MESSAGES_TOTAL,
)
from app.models.outbox_message import OutboxMessage
from app.services.account_action_tokens import as_utc, utc_now
from app.services.email_delivery import EmailSender
from app.services.outbox import decrypt_email_payload

logger = logging.getLogger("fastapi-production-api.outbox_worker")


@dataclass(frozen=True)
class ClaimedMessage:
    id: UUID
    message_type: str
    encryption_version: int
    payload_encrypted: bytes
    payload_expires_at: datetime
    attempt_count: int
    lease_recovered: bool


def claim_messages(
    session_factory: sessionmaker,
    lease_owner: str,
    *,
    now: datetime | None = None,
) -> list[ClaimedMessage]:
    claimed_at = now or utc_now()
    lease_expires_at = claimed_at + timedelta(seconds=settings.OUTBOX_LEASE_SECONDS)
    with session_factory() as db:
        try:
            messages = (
                db.query(OutboxMessage)
                .filter(
                    or_(
                        and_(
                            OutboxMessage.status == "pending",
                            OutboxMessage.available_at <= claimed_at,
                        ),
                        and_(
                            OutboxMessage.status == "processing",
                            OutboxMessage.lease_expires_at <= claimed_at,
                        ),
                    )
                )
                .order_by(OutboxMessage.available_at, OutboxMessage.created_at)
                .with_for_update(skip_locked=True)
                .limit(settings.OUTBOX_BATCH_SIZE)
                .all()
            )
            result = []
            for message in messages:
                recovered = message.status == "processing"
                message.status = "processing"
                message.lease_owner = lease_owner
                message.lease_expires_at = lease_expires_at
                message.attempt_count += 1
                message.updated_at = claimed_at
                result.append(
                    ClaimedMessage(
                        id=message.id,
                        message_type=message.message_type,
                        encryption_version=message.encryption_version,
                        payload_encrypted=message.payload_encrypted,
                        payload_expires_at=as_utc(message.payload_expires_at),
                        attempt_count=message.attempt_count,
                        lease_recovered=recovered,
                    )
                )
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise


def _owned_update(
    db: Session,
    message: ClaimedMessage,
    lease_owner: str,
    values: dict,
) -> bool:
    result = db.execute(
        update(OutboxMessage)
        .where(
            OutboxMessage.id == message.id,
            OutboxMessage.status == "processing",
            OutboxMessage.lease_owner == lease_owner,
        )
        .values(**values)
    )
    return result.rowcount == 1


def mark_succeeded(
    session_factory: sessionmaker,
    message: ClaimedMessage,
    lease_owner: str,
    *,
    now: datetime | None = None,
) -> bool:
    completed_at = now or utc_now()
    with session_factory() as db:
        try:
            updated = _owned_update(
                db,
                message,
                lease_owner,
                {
                    "status": "succeeded",
                    "payload_encrypted": None,
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "failure_category": None,
                    "updated_at": completed_at,
                    "terminal_at": completed_at,
                },
            )
            db.commit()
            return updated
        except Exception:
            db.rollback()
            raise


def _retry_delay(message: ClaimedMessage) -> int:
    base = settings.OUTBOX_BACKOFF_BASE_SECONDS
    maximum = settings.OUTBOX_BACKOFF_MAX_SECONDS
    exponential = min(maximum, base * (2 ** (message.attempt_count - 1)))
    jitter_limit = max(1, min(base, exponential // 4))
    digest = hashlib.sha256(
        f"{message.id}:{message.attempt_count}".encode("ascii")
    ).digest()
    jitter = int.from_bytes(digest[:2], "big") % (jitter_limit + 1)
    return min(maximum, exponential + jitter)


def mark_failed(
    session_factory: sessionmaker,
    message: ClaimedMessage,
    lease_owner: str,
    *,
    category: str,
    retryable: bool,
    now: datetime | None = None,
) -> str | None:
    failed_at = now or utc_now()
    terminal = (
        not retryable
        or message.attempt_count >= settings.OUTBOX_MAX_ATTEMPTS
        or message.payload_expires_at <= failed_at
    )
    if terminal:
        outcome = "dead_letter"
        values = {
            "status": "dead_letter",
            "payload_encrypted": None,
            "available_at": failed_at,
            "lease_owner": None,
            "lease_expires_at": None,
            "failure_category": category,
            "updated_at": failed_at,
            "terminal_at": failed_at,
        }
    else:
        outcome = "retried"
        values = {
            "status": "pending",
            "available_at": failed_at + timedelta(seconds=_retry_delay(message)),
            "lease_owner": None,
            "lease_expires_at": None,
            "failure_category": category,
            "updated_at": failed_at,
        }

    with session_factory() as db:
        try:
            updated = _owned_update(db, message, lease_owner, values)
            db.commit()
            return outcome if updated else None
        except Exception:
            db.rollback()
            raise


class OutboxWorker:
    def __init__(self, session_factory: sessionmaker, sender: EmailSender, owner: str):
        self.session_factory = session_factory
        self.sender = sender
        self.owner = owner
        self.stop_requested_at: float | None = None

    def request_stop(self) -> None:
        if self.stop_requested_at is None:
            self.stop_requested_at = time.monotonic()

    def _grace_expired(self) -> bool:
        return self.stop_requested_at is not None and (
            time.monotonic() - self.stop_requested_at
            >= settings.OUTBOX_SHUTDOWN_GRACE_SECONDS
        )

    def run_once(self) -> int:
        if self.stop_requested_at is not None:
            return 0
        messages = claim_messages(self.session_factory, self.owner)
        for message in messages:
            OUTBOX_MESSAGES_TOTAL.labels(
                message_type=message.message_type,
                outcome="claimed",
            ).inc()
            if self._grace_expired():
                break
            self._process(message)
        return len(messages)

    def _process(self, message: ClaimedMessage) -> None:
        if message.lease_recovered:
            OUTBOX_MESSAGES_TOTAL.labels(
                message_type=message.message_type,
                outcome="lease_recovered",
            ).inc()
        if message.payload_expires_at <= utc_now():
            self._fail(message, category="expired", retryable=False)
            return

        payload_model = OutboxMessage(
            encryption_version=message.encryption_version,
            payload_encrypted=message.payload_encrypted,
        )
        try:
            payload = decrypt_email_payload(payload_model)
        except ValueError:
            self._fail(message, category="invalid_payload", retryable=False)
            return

        started_at = time.perf_counter()
        try:
            self.sender.send_outbox(
                message.message_type,
                payload["recipient"],
                payload["token"],
                payload["action_url"],
            )
        except (smtplib.SMTPException, OSError, TimeoutError):
            self._fail(message, category="smtp", retryable=True)
            return
        finally:
            OUTBOX_DELIVERY_DURATION_SECONDS.labels(
                message_type=message.message_type
            ).observe(time.perf_counter() - started_at)

        if mark_succeeded(self.session_factory, message, self.owner):
            self._record(message, "succeeded")
        else:
            self._record(message, "stale_owner")

    def _fail(self, message: ClaimedMessage, *, category: str, retryable: bool) -> None:
        outcome = mark_failed(
            self.session_factory,
            message,
            self.owner,
            category=category,
            retryable=retryable,
        )
        OUTBOX_FAILURES_TOTAL.labels(category=category).inc()
        if category == "expired":
            OUTBOX_MESSAGES_TOTAL.labels(
                message_type=message.message_type,
                outcome="expired",
            ).inc()
        self._record(message, outcome or "stale_owner", category)

    @staticmethod
    def _record(
        message: ClaimedMessage,
        outcome: str,
        category: str | None = None,
    ) -> None:
        OUTBOX_MESSAGES_TOTAL.labels(
            message_type=message.message_type,
            outcome=outcome,
        ).inc()
        logger.info(
            "outbox_worker_event",
            extra={
                "outbox_message_type": message.message_type,
                "outbox_attempt": message.attempt_count,
                "outbox_event": outcome,
                "outbox_failure_category": category,
            },
        )
