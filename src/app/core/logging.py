import json
import logging
import sys
from datetime import UTC, datetime

from opentelemetry import trace

from app.core.config import settings
from app.core.request_context import get_request_id


def _current_trace_context() -> tuple[str | None, str | None]:
    span = trace.get_current_span()
    span_context = span.get_span_context()

    if not span_context.is_valid:
        return None, None

    return (
        f"{span_context.trace_id:032x}",
        f"{span_context.span_id:016x}",
    )


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        trace_id, span_id = _current_trace_context()

        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                UTC,
            ).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(
                record,
                "request_id",
                get_request_id(),
            ),
        }

        if trace_id is not None:
            payload["trace_id"] = trace_id

        if span_id is not None:
            payload["span_id"] = span_id

        for field in (
            "method",
            "path",
            "route",
            "status_code",
            "duration_ms",
            "rate_limit_backend",
            "rate_limit_policy",
            "rate_limit_operation",
            "outbox_message_type",
            "outbox_attempt",
            "outbox_event",
            "outbox_failure_category",
            "oidc_cache_event",
            "oidc_cache_document",
            "tracing_service",
            "tracing_environment",
        ):
            value = getattr(record, field, None)

            if value is not None:
                payload[field] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )


def setup_logging() -> None:
    log_level = getattr(
        logging,
        settings.LOG_LEVEL.upper(),
        logging.INFO,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)


logger = logging.getLogger("fastapi-production-api")
