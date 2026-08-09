import smtplib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.models.outbox_message import OutboxMessage
from app.services.account_action_tokens import utc_now
from app.services.outbox import EMAIL_VERIFICATION_MESSAGE, enqueue_email_delivery
from app.services.outbox_worker import (
    OutboxWorker,
    claim_messages,
    mark_succeeded,
)


class CapturingSender:
    def __init__(self) -> None:
        self.deliveries = []

    def send_outbox(self, message_type, recipient, token, action_url) -> None:
        self.deliveries.append((message_type, recipient, token, action_url))


class FailingSender:
    def send_outbox(self, message_type, recipient, token, action_url) -> None:
        raise smtplib.SMTPConnectError(421, "provider unavailable")


@pytest.fixture(autouse=True)
def isolated_outbox(monkeypatch):
    monkeypatch.setattr(
        settings,
        "OUTBOX_ENCRYPTION_KEY",
        SecretStr(Fernet.generate_key().decode("ascii")),
    )
    monkeypatch.setattr(settings, "OUTBOX_BATCH_SIZE", 10)
    monkeypatch.setattr(settings, "OUTBOX_LEASE_SECONDS", 30)
    monkeypatch.setattr(settings, "OUTBOX_MAX_ATTEMPTS", 5)
    monkeypatch.setattr(settings, "OUTBOX_BACKOFF_BASE_SECONDS", 1)
    monkeypatch.setattr(settings, "OUTBOX_BACKOFF_MAX_SECONDS", 10)
    with SessionLocal() as db:
        db.query(OutboxMessage).delete()
        db.commit()
    yield
    with SessionLocal() as db:
        db.query(OutboxMessage).delete()
        db.commit()


def enqueue_message(*, expires_delta: timedelta = timedelta(minutes=5)):
    token = f"token-{uuid4().hex}"
    with SessionLocal() as db:
        message = enqueue_email_delivery(
            db,
            message_type=EMAIL_VERIFICATION_MESSAGE,
            recipient=f"worker-{uuid4().hex}@example.com",
            token=token,
            token_hash=uuid4().hex * 2,
            action_url="https://app.example.com/verify-email",
            expires_at=utc_now() + expires_delta,
        )
        db.commit()
        return message.id, token


def test_postgresql_sessions_use_utc():
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL is required to inspect the session timezone")
    with SessionLocal() as db:
        assert db.execute(text("SHOW TIME ZONE")).scalar_one() == "UTC"


def test_two_workers_claim_disjoint_batches(monkeypatch):
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL is required to exercise SKIP LOCKED concurrency")
    monkeypatch.setattr(settings, "OUTBOX_BATCH_SIZE", 2)
    message_ids = {enqueue_message()[0] for _ in range(4)}

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(claim_messages, SessionLocal, "worker-a")
        second = executor.submit(claim_messages, SessionLocal, "worker-b")
        claimed = first.result() + second.result()

    assert {message.id for message in claimed} == message_ids
    assert len({message.id for message in claimed}) == 4


def test_active_lease_is_protected_and_expired_lease_is_recovered():
    message_id, _ = enqueue_message()
    first = claim_messages(SessionLocal, "worker-a")

    assert [message.id for message in first] == [message_id]
    assert claim_messages(SessionLocal, "worker-b") == []

    with SessionLocal() as db:
        stored = db.get(OutboxMessage, message_id)
        stored.lease_expires_at = utc_now() - timedelta(seconds=1)
        db.commit()

    recovered = claim_messages(SessionLocal, "worker-b")

    assert [message.id for message in recovered] == [message_id]
    assert recovered[0].lease_recovered is True
    assert mark_succeeded(SessionLocal, first[0], "worker-a") is False
    assert mark_succeeded(SessionLocal, recovered[0], "worker-b") is True


def test_successful_delivery_purges_sensitive_payload():
    message_id, raw_token = enqueue_message()
    sender = CapturingSender()

    processed = OutboxWorker(SessionLocal, sender, "worker-a").run_once()

    assert processed == 1
    assert sender.deliveries[0][2] == raw_token
    with SessionLocal() as db:
        stored = db.get(OutboxMessage, message_id)
        assert stored.status == "succeeded"
        assert stored.payload_encrypted is None
        assert stored.terminal_at is not None


def test_retry_backoff_then_dead_letter_purges_payload(monkeypatch):
    monkeypatch.setattr(settings, "OUTBOX_MAX_ATTEMPTS", 2)
    message_id, _ = enqueue_message()
    worker = OutboxWorker(SessionLocal, FailingSender(), "worker-a")

    assert worker.run_once() == 1
    with SessionLocal() as db:
        stored = db.get(OutboxMessage, message_id)
        assert stored.status == "pending"
        assert stored.attempt_count == 1
        assert stored.available_at > stored.updated_at
        assert stored.payload_encrypted is not None
        stored.available_at = utc_now() - timedelta(seconds=1)
        db.commit()

    assert worker.run_once() == 1
    with SessionLocal() as db:
        stored = db.get(OutboxMessage, message_id)
        assert stored.status == "dead_letter"
        assert stored.failure_category == "smtp"
        assert stored.payload_encrypted is None


def test_expired_payload_is_never_delivered_and_is_purged():
    message_id, _ = enqueue_message(expires_delta=timedelta(seconds=-1))
    sender = CapturingSender()

    OutboxWorker(SessionLocal, sender, "worker-a").run_once()

    assert sender.deliveries == []
    with SessionLocal() as db:
        stored = db.get(OutboxMessage, message_id)
        assert stored.status == "dead_letter"
        assert stored.failure_category == "expired"
        assert stored.payload_encrypted is None


def test_shutdown_stops_new_claims_and_leaves_pending_work():
    message_id, _ = enqueue_message()
    worker = OutboxWorker(SessionLocal, CapturingSender(), "worker-a")
    worker.request_stop()

    assert worker.run_once() == 0
    with SessionLocal() as db:
        assert db.get(OutboxMessage, message_id).status == "pending"
