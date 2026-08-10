import json
import logging

from opentelemetry.sdk.trace import TracerProvider

from app.core.logging import JsonFormatter


def _format_record(message: str = "test-message") -> dict[str, object]:
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )

    formatter = JsonFormatter()
    return json.loads(formatter.format(record))


def test_json_log_without_active_span_has_no_trace_fields():
    payload = _format_record()

    assert payload["message"] == "test-message"
    assert "trace_id" not in payload
    assert "span_id" not in payload


def test_json_log_contains_trace_and_span_ids_inside_active_span():
    provider = TracerProvider()
    tracer = provider.get_tracer("test.logging")

    with tracer.start_as_current_span("logging-test") as span:
        span_context = span.get_span_context()
        payload = _format_record("inside-span")

    assert payload["message"] == "inside-span"
    assert payload["trace_id"] == f"{span_context.trace_id:032x}"
    assert payload["span_id"] == f"{span_context.span_id:016x}"

    provider.shutdown()


def test_json_log_preserves_request_and_operational_fields():
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="worker-event",
        args=(),
        exc_info=None,
    )

    record.request_id = "request-123"
    record.outbox_message_type = "email_verification.v1"
    record.outbox_attempt = 2
    record.outbox_event = "retried"
    record.tracing_service = "fastapi-production-api"
    record.tracing_environment = "testing"

    formatter = JsonFormatter()
    payload = json.loads(formatter.format(record))

    assert payload["request_id"] == "request-123"
    assert payload["outbox_message_type"] == "email_verification.v1"
    assert payload["outbox_attempt"] == 2
    assert payload["outbox_event"] == "retried"
    assert payload["tracing_service"] == "fastapi-production-api"
    assert payload["tracing_environment"] == "testing"


def test_json_log_formats_exception():
    try:
        raise RuntimeError("expected failure")
    except RuntimeError:
        import sys

        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test.logger",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="operation-failed",
        args=(),
        exc_info=exc_info,
    )

    formatter = JsonFormatter()
    payload = json.loads(formatter.format(record))

    assert payload["message"] == "operation-failed"
    assert "RuntimeError: expected failure" in payload["exception"]
