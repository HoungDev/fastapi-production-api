from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from app.core.config import settings

logger = logging.getLogger("fastapi-production-api.tracing")

_provider: TracerProvider | None = None
_instrumented_app: FastAPI | None = None
_httpx_instrumented = False
_redis_instrumented = False
_sqlalchemy_instrumented = False


def _sanitize_url(value: str) -> str:
    parsed = urlsplit(value)

    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"

    port = f":{parsed.port}" if parsed.port is not None else ""
    netloc = f"{hostname}{port}"

    return urlunsplit(
        (
            parsed.scheme,
            netloc,
            parsed.path or "/",
            "",
            "",
        )
    )


def _otlp_trace_endpoint() -> str:
    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT.rstrip("/")
    if endpoint.endswith("/v1/traces"):
        return endpoint
    return f"{endpoint}/v1/traces"


def _server_request_hook(
    span: Span,
    scope: dict[str, Any],
) -> None:
    if not span or not span.is_recording():
        return

    path = scope.get("path")
    if not isinstance(path, str) or not path:
        path = "/"

    scheme = scope.get("scheme")
    if not isinstance(scheme, str) or not scheme:
        scheme = "http"

    server = scope.get("server")
    host = "localhost"
    port: int | None = None

    if (
        isinstance(server, (tuple, list))
        and len(server) >= 2
        and isinstance(server[0], str)
    ):
        host = server[0]
        if isinstance(server[1], int):
            port = server[1]

    if ":" in host and not host.startswith("["):
        host = f"[{host}]"

    default_port = (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    )
    port_suffix = "" if port is None or default_port else f":{port}"

    safe_url = f"{scheme}://{host}{port_suffix}{path}"

    # Override both current and legacy HTTP URL attributes so query strings
    # such as OIDC code/state never remain in exported request spans.
    span.set_attribute("url.full", safe_url)
    span.set_attribute("url.path", path)
    span.set_attribute("url.query", "")
    span.set_attribute("http.url", safe_url)
    span.set_attribute("http.target", path)


def _httpx_request_hook(
    span: Span,
    request: Any,
) -> None:
    if not span or not span.is_recording():
        return

    url = getattr(request, "url", None)
    if url is None:
        return

    safe_url = _sanitize_url(str(url))
    safe_path = urlsplit(safe_url).path or "/"

    # Do not copy headers, request bodies, credentials, or query parameters.
    span.set_attribute("url.full", safe_url)
    span.set_attribute("url.path", safe_path)
    span.set_attribute("url.query", "")
    span.set_attribute("http.url", safe_url)
    span.set_attribute("http.target", safe_path)


async def _httpx_async_request_hook(
    span: Span,
    request: Any,
) -> None:
    _httpx_request_hook(span, request)


def _instrument_fastapi(
    app: FastAPI,
    provider: TracerProvider,
) -> None:
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        server_request_hook=_server_request_hook,
        http_capture_headers_server_request=[],
        http_capture_headers_server_response=[],
        exclude_spans=["send", "receive"],
    )


def _instrument_httpx(provider: TracerProvider) -> None:
    global _httpx_instrumented

    if _httpx_instrumented:
        return

    HTTPXClientInstrumentor().instrument(
        tracer_provider=provider,
        request_hook=_httpx_request_hook,
        async_request_hook=_httpx_async_request_hook,
    )
    _httpx_instrumented = True


def _instrument_redis(provider: TracerProvider) -> None:
    global _redis_instrumented

    if _redis_instrumented:
        return

    RedisInstrumentor().instrument(
        tracer_provider=provider,
    )
    _redis_instrumented = True


_TRACEPARENT_MAX_LENGTH = 256
_TRACESTATE_MAX_LENGTH = 512

_trace_context_propagator = TraceContextTextMapPropagator()


def capture_trace_context() -> tuple[str | None, str | None]:
    carrier: dict[str, str] = {}
    _trace_context_propagator.inject(carrier)

    traceparent = carrier.get("traceparent")
    tracestate = carrier.get("tracestate")

    if traceparent is not None and len(traceparent) > _TRACEPARENT_MAX_LENGTH:
        logger.warning("trace_context_traceparent_rejected")
        traceparent = None
        tracestate = None

    if tracestate is not None and len(tracestate) > _TRACESTATE_MAX_LENGTH:
        logger.warning("trace_context_tracestate_rejected")
        tracestate = None

    return traceparent, tracestate


def extract_trace_context(
    traceparent: str | None,
    tracestate: str | None,
) -> Context:
    carrier: dict[str, str] = {}

    if traceparent and len(traceparent) <= _TRACEPARENT_MAX_LENGTH:
        carrier["traceparent"] = traceparent

    if tracestate and len(tracestate) <= _TRACESTATE_MAX_LENGTH:
        carrier["tracestate"] = tracestate

    try:
        return _trace_context_propagator.extract(carrier)
    except Exception:
        logger.exception("trace_context_extract_failed")
        return Context()


def _instrument_sqlalchemy(provider: TracerProvider) -> None:
    global _sqlalchemy_instrumented

    if _sqlalchemy_instrumented:
        return

    from app.db.session import engine

    SQLAlchemyInstrumentor().instrument(
        engine=engine,
        tracer_provider=provider,
    )
    _sqlalchemy_instrumented = True


def setup_tracing(app: FastAPI) -> TracerProvider | None:
    global _instrumented_app, _provider

    if not settings.TRACING_ENABLED:
        return None

    if _provider is not None:
        if _instrumented_app is None:
            _instrument_fastapi(app, _provider)
            _instrumented_app = app
        return _provider

    try:
        resource = Resource.create(
            {
                "service.name": settings.OTEL_SERVICE_NAME.strip(),
                "deployment.environment.name": settings.ENVIRONMENT.lower(),
            }
        )

        sampler = ParentBased(TraceIdRatioBased(settings.OTEL_TRACE_SAMPLE_RATIO))

        provider = TracerProvider(
            resource=resource,
            sampler=sampler,
        )

        exporter = OTLPSpanExporter(
            endpoint=_otlp_trace_endpoint(),
            timeout=settings.OTEL_EXPORT_TIMEOUT_SECONDS,
        )

        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)

        _instrument_fastapi(app, provider)
        _instrument_httpx(provider)
        _instrument_redis(provider)
        _instrument_sqlalchemy(provider)

        _provider = provider
        _instrumented_app = app

        logger.info(
            "tracing_initialized",
            extra={
                "tracing_service": settings.OTEL_SERVICE_NAME.strip(),
                "tracing_environment": settings.ENVIRONMENT.lower(),
            },
        )

        return provider

    except Exception:
        logger.exception("tracing_initialization_failed")
        return None


def get_tracer(name: str):
    provider = _provider
    if provider is None:
        return None
    return provider.get_tracer(name)


def force_flush_tracing() -> bool:
    provider = _provider
    if provider is None:
        return True

    timeout_millis = int(settings.OTEL_EXPORT_TIMEOUT_SECONDS * 1000)

    try:
        return provider.force_flush(timeout_millis=timeout_millis)
    except Exception:
        logger.exception("tracing_force_flush_failed")
        return False


def shutdown_tracing() -> None:
    global _httpx_instrumented, _instrumented_app, _provider
    global _redis_instrumented, _sqlalchemy_instrumented

    provider = _provider
    app = _instrumented_app

    _provider = None
    _instrumented_app = None

    if app is not None:
        try:
            FastAPIInstrumentor.uninstrument_app(app)
        except Exception:
            logger.exception("tracing_fastapi_uninstrument_failed")

    if _httpx_instrumented:
        try:
            HTTPXClientInstrumentor().uninstrument()
        except Exception:
            logger.exception("tracing_httpx_uninstrument_failed")
        finally:
            _httpx_instrumented = False

    if _redis_instrumented:
        try:
            RedisInstrumentor().uninstrument()
        except Exception:
            logger.exception("tracing_redis_uninstrument_failed")
        finally:
            _redis_instrumented = False

    if _sqlalchemy_instrumented:
        try:
            SQLAlchemyInstrumentor().uninstrument()
        except Exception:
            logger.exception("tracing_sqlalchemy_uninstrument_failed")
        finally:
            _sqlalchemy_instrumented = False

    if provider is None:
        return

    force_flush_timeout_millis = int(settings.OTEL_EXPORT_TIMEOUT_SECONDS * 1000)

    try:
        provider.force_flush(
            timeout_millis=force_flush_timeout_millis,
        )
    except Exception:
        logger.exception("tracing_shutdown_flush_failed")

    try:
        provider.shutdown()
    except Exception:
        logger.exception("tracing_shutdown_failed")
