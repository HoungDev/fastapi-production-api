import smtplib
from datetime import timedelta
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pydantic import SecretStr

from app.core import tracing
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.outbox_message import OutboxMessage
from app.services.account_action_tokens import utc_now
from app.services.outbox import (
    EMAIL_VERIFICATION_MESSAGE,
    enqueue_email_delivery,
)
from app.services.outbox_worker import OutboxWorker


class CapturingSender:
    def __init__(self) -> None:
        self.deliveries: list[tuple[str, str, str, str]] = []

    def send_outbox(
        self,
        message_type: str,
        recipient: str,
        token: str,
        action_url: str,
    ) -> None:
        self.deliveries.append(
            (
                message_type,
                recipient,
                token,
                action_url,
            )
        )


class FailingSender:
    def send_outbox(
        self,
        message_type: str,
        recipient: str,
        token: str,
        action_url: str,
    ) -> None:
        raise smtplib.SMTPConnectError(
            421,
            "provider unavailable",
        )


@pytest.fixture(autouse=True)
def isolated_traced_outbox(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        settings,
        "OUTBOX_ENCRYPTION_KEY",
        SecretStr(Fernet.generate_key().decode("ascii")),
    )
    monkeypatch.setattr(
        settings,
        "OUTBOX_BATCH_SIZE",
        10,
    )
    monkeypatch.setattr(
        settings,
        "OUTBOX_LEASE_SECONDS",
        30,
    )
    monkeypatch.setattr(
        settings,
        "OUTBOX_MAX_ATTEMPTS",
        5,
    )
    monkeypatch.setattr(
        settings,
        "OUTBOX_BACKOFF_BASE_SECONDS",
        1,
    )
    monkeypatch.setattr(
        settings,
        "OUTBOX_BACKOFF_MAX_SECONDS",
        10,
    )

    monkeypatch.setattr(
        tracing,
        "_provider",
        None,
    )

    with SessionLocal() as db:
        db.query(OutboxMessage).delete()
        db.commit()

    yield

    monkeypatch.setattr(
        tracing,
        "_provider",
        None,
    )

    with SessionLocal() as db:
        db.query(OutboxMessage).delete()
        db.commit()


def _provider_with_exporter():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def _enqueue_message() -> tuple[object, str]:
    token = f"token-{uuid4().hex}"

    with SessionLocal() as db:
        message = enqueue_email_delivery(
            db,
            message_type=EMAIL_VERIFICATION_MESSAGE,
            recipient=f"trace-{uuid4().hex}@example.com",
            token=token,
            token_hash=uuid4().hex * 2,
            action_url=("https://app.example.com/verify-email"),
            expires_at=(utc_now() + timedelta(minutes=5)),
        )
        db.commit()
        return message.id, token


def test_enqueue_captures_current_w3c_trace_context(
    monkeypatch: pytest.MonkeyPatch,
):
    provider, exporter = _provider_with_exporter()
    tracer = provider.get_tracer("test.outbox.enqueue")

    with tracer.start_as_current_span("request-parent") as parent_span:
        parent_context = parent_span.get_span_context()

        message_id, _ = _enqueue_message()

    with SessionLocal() as db:
        stored = db.get(
            OutboxMessage,
            message_id,
        )

        assert stored is not None
        assert stored.traceparent is not None
        assert len(stored.traceparent) <= 256
        assert stored.traceparent.startswith("00-")

        trace_id_hex = f"{parent_context.trace_id:032x}"

        assert trace_id_hex in stored.traceparent

    provider.shutdown()
    assert exporter.get_finished_spans()


def test_worker_continues_original_trace_and_purges_context(
    monkeypatch: pytest.MonkeyPatch,
):
    provider, exporter = _provider_with_exporter()
    tracer = provider.get_tracer("test.outbox.request")

    with tracer.start_as_current_span("request-parent") as parent_span:
        parent_context = parent_span.get_span_context()
        message_id, raw_token = _enqueue_message()

    monkeypatch.setattr(
        tracing,
        "_provider",
        provider,
    )

    sender = CapturingSender()

    processed = OutboxWorker(
        SessionLocal,
        sender,
        "worker-a",
    ).run_once()

    assert processed == 1
    assert sender.deliveries[0][2] == raw_token

    finished = exporter.get_finished_spans()

    worker_spans = [span for span in finished if span.name == "outbox.process"]

    assert len(worker_spans) == 1

    worker_span = worker_spans[0]

    assert worker_span.context.trace_id == parent_context.trace_id
    assert worker_span.parent is not None
    assert worker_span.parent.span_id == parent_context.span_id

    assert worker_span.attributes["outbox.message_type"] == EMAIL_VERIFICATION_MESSAGE
    assert worker_span.attributes["outbox.attempt"] == 1

    with SessionLocal() as db:
        stored = db.get(
            OutboxMessage,
            message_id,
        )

        assert stored.status == "succeeded"
        assert stored.traceparent is None
        assert stored.tracestate is None
        assert stored.payload_encrypted is None

    provider.shutdown()


def test_retry_preserves_trace_context_until_terminal_state(
    monkeypatch: pytest.MonkeyPatch,
):
    provider, _ = _provider_with_exporter()
    tracer = provider.get_tracer("test.outbox.retry")

    monkeypatch.setattr(
        settings,
        "OUTBOX_MAX_ATTEMPTS",
        2,
    )

    with tracer.start_as_current_span("request-parent"):
        message_id, _ = _enqueue_message()

    monkeypatch.setattr(
        tracing,
        "_provider",
        provider,
    )

    worker = OutboxWorker(
        SessionLocal,
        FailingSender(),
        "worker-a",
    )

    assert worker.run_once() == 1

    with SessionLocal() as db:
        stored = db.get(
            OutboxMessage,
            message_id,
        )

        assert stored.status == "pending"
        assert stored.attempt_count == 1
        assert stored.traceparent is not None

        original_traceparent = stored.traceparent
        original_tracestate = stored.tracestate

        stored.available_at = utc_now() - timedelta(seconds=1)
        db.commit()

    assert worker.run_once() == 1

    with SessionLocal() as db:
        stored = db.get(
            OutboxMessage,
            message_id,
        )

        assert stored.status == "dead_letter"
        assert stored.attempt_count == 2
        assert stored.traceparent is None
        assert stored.tracestate is None
        assert stored.payload_encrypted is None

    assert original_traceparent is not None
    assert original_tracestate is None or isinstance(
        original_tracestate,
        str,
    )

    provider.shutdown()


def test_worker_without_tracing_preserves_existing_behavior(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        tracing,
        "_provider",
        None,
    )

    message_id, raw_token = _enqueue_message()

    sender = CapturingSender()

    processed = OutboxWorker(
        SessionLocal,
        sender,
        "worker-a",
    ).run_once()

    assert processed == 1
    assert sender.deliveries[0][2] == raw_token

    with SessionLocal() as db:
        stored = db.get(
            OutboxMessage,
            message_id,
        )

        assert stored.status == "succeeded"
        assert stored.payload_encrypted is None
