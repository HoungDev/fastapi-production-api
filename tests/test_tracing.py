import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from opentelemetry.context import Context
from pydantic import ValidationError

from app.core import tracing
from app.core.config import Settings


class RecordingSpan:
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}

    def is_recording(self) -> bool:
        return True

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value


class NonRecordingSpan:
    def is_recording(self) -> bool:
        return False

    def set_attribute(self, key: str, value: object) -> None:
        raise AssertionError("non-recording span must not receive attributes")


class FakeProvider:
    def __init__(self) -> None:
        self.flush_calls: list[int] = []
        self.shutdown_calls = 0
        self.processors: list[object] = []
        self.constructor_kwargs: dict[str, object] = {}

    def force_flush(self, timeout_millis: int) -> bool:
        self.flush_calls.append(timeout_millis)
        return True

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    def get_tracer(self, name: str):
        return f"tracer:{name}"

    def add_span_processor(self, processor: object) -> None:
        self.processors.append(processor)


@pytest.fixture(autouse=True)
def reset_tracing_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tracing, "_provider", None)
    monkeypatch.setattr(tracing, "_instrumented_app", None)
    monkeypatch.setattr(tracing, "_httpx_instrumented", False)
    monkeypatch.setattr(tracing, "_redis_instrumented", False)
    monkeypatch.setattr(tracing, "_sqlalchemy_instrumented", False)


def _settings_kwargs() -> dict[str, object]:
    return {
        "DATABASE_URL": "sqlite:///test.db",
        "SECRET_KEY": "development-secret",
        "_env_file": None,
    }


def test_sanitize_url_removes_query_fragment_and_credentials():
    result = tracing._sanitize_url(
        "https://user:password@example.com:8443/callback"
        "?code=secret-code&state=secret-state#fragment"
    )

    assert result == "https://example.com:8443/callback"
    assert "password" not in result
    assert "code=" not in result
    assert "state=" not in result


def test_sanitize_url_preserves_safe_path():
    assert (
        tracing._sanitize_url("https://example.com/api/v1/users")
        == "https://example.com/api/v1/users"
    )


def test_sanitize_url_handles_ipv6_and_empty_path():
    result = tracing._sanitize_url(
        "https://user:password@[2001:db8::1]:8443?token=secret"
    )

    assert result == "https://[2001:db8::1]:8443/"
    assert "secret" not in result
    assert "password" not in result


def test_otlp_trace_endpoint_appends_standard_path(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        tracing.settings,
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://collector:4318",
    )

    assert tracing._otlp_trace_endpoint() == "http://collector:4318/v1/traces"


def test_otlp_trace_endpoint_does_not_duplicate_path(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        tracing.settings,
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://collector:4318/v1/traces",
    )

    assert tracing._otlp_trace_endpoint() == "http://collector:4318/v1/traces"


def test_server_request_hook_removes_query_string():
    span = RecordingSpan()

    tracing._server_request_hook(
        span,
        {
            "path": "/auth/oidc/callback",
            "scheme": "https",
            "server": ("api.example.com", 443),
            "query_string": b"code=secret&state=secret",
        },
    )

    assert span.attributes["url.full"] == ("https://api.example.com/auth/oidc/callback")
    assert span.attributes["url.query"] == ""
    assert "secret" not in str(span.attributes)


def test_server_request_hook_ignores_non_recording_span():
    tracing._server_request_hook(
        NonRecordingSpan(),
        {
            "path": "/secret",
            "scheme": "https",
            "server": ("api.example.com", 443),
        },
    )


def test_server_request_hook_uses_safe_fallbacks():
    span = RecordingSpan()

    tracing._server_request_hook(
        span,
        {
            "path": None,
            "scheme": None,
            "server": None,
        },
    )

    assert span.attributes["url.full"] == "http://localhost/"
    assert span.attributes["url.path"] == "/"
    assert span.attributes["url.query"] == ""


def test_server_request_hook_handles_ipv6():
    span = RecordingSpan()

    tracing._server_request_hook(
        span,
        {
            "path": "/health",
            "scheme": "http",
            "server": ("2001:db8::1", 8000),
        },
    )

    assert span.attributes["url.full"] == ("http://[2001:db8::1]:8000/health")


def test_httpx_request_hook_removes_sensitive_query_values():
    span = RecordingSpan()
    request = httpx.Request(
        "GET",
        "https://provider.example/oauth/token"
        "?code=secret-code&client_secret=secret-value",
    )

    tracing._httpx_request_hook(span, request)

    assert span.attributes["url.full"] == ("https://provider.example/oauth/token")
    assert span.attributes["url.query"] == ""
    assert "secret-code" not in str(span.attributes)
    assert "secret-value" not in str(span.attributes)


def test_httpx_request_hook_ignores_non_recording_span():
    request = httpx.Request(
        "GET",
        "https://provider.example/callback?code=secret",
    )

    tracing._httpx_request_hook(NonRecordingSpan(), request)


def test_httpx_request_hook_ignores_object_without_url():
    span = RecordingSpan()

    tracing._httpx_request_hook(span, object())

    assert span.attributes == {}


def test_httpx_async_request_hook_uses_same_sanitization():
    span = RecordingSpan()
    request = httpx.Request(
        "GET",
        "https://provider.example/callback?state=sensitive",
    )

    asyncio.run(tracing._httpx_async_request_hook(span, request))

    assert span.attributes["url.full"] == ("https://provider.example/callback")
    assert span.attributes["url.query"] == ""
    assert "sensitive" not in str(span.attributes)


def test_instrument_fastapi_calls_instrumentor(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[dict[str, object]] = []

    class FakeFastAPIInstrumentor:
        @staticmethod
        def instrument_app(app, **kwargs):
            calls.append({"app": app, **kwargs})

    monkeypatch.setattr(
        tracing,
        "FastAPIInstrumentor",
        FakeFastAPIInstrumentor,
    )

    app = FastAPI()
    provider = FakeProvider()

    tracing._instrument_fastapi(app, provider)

    assert len(calls) == 1
    assert calls[0]["app"] is app
    assert calls[0]["tracer_provider"] is provider
    assert calls[0]["server_request_hook"] is tracing._server_request_hook
    assert calls[0]["http_capture_headers_server_request"] == []
    assert calls[0]["http_capture_headers_server_response"] == []


def test_instrument_httpx_runs_once(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[dict[str, object]] = []

    class FakeHTTPXInstrumentor:
        def instrument(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(
        tracing,
        "HTTPXClientInstrumentor",
        FakeHTTPXInstrumentor,
    )

    provider = FakeProvider()

    tracing._instrument_httpx(provider)
    tracing._instrument_httpx(provider)

    assert len(calls) == 1
    assert tracing._httpx_instrumented is True


def test_instrument_redis_runs_once(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[dict[str, object]] = []

    class FakeRedisInstrumentor:
        def instrument(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(
        tracing,
        "RedisInstrumentor",
        FakeRedisInstrumentor,
    )

    provider = FakeProvider()

    tracing._instrument_redis(provider)
    tracing._instrument_redis(provider)

    assert len(calls) == 1
    assert tracing._redis_instrumented is True


def test_instrument_sqlalchemy_runs_once(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[dict[str, object]] = []

    class FakeSQLAlchemyInstrumentor:
        def instrument(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(
        tracing,
        "SQLAlchemyInstrumentor",
        FakeSQLAlchemyInstrumentor,
    )

    provider = FakeProvider()

    tracing._instrument_sqlalchemy(provider)
    tracing._instrument_sqlalchemy(provider)

    assert len(calls) == 1
    assert "engine" in calls[0]
    assert calls[0]["tracer_provider"] is provider
    assert tracing._sqlalchemy_instrumented is True


def test_setup_tracing_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(tracing.settings, "TRACING_ENABLED", False)

    app = FastAPI()

    assert tracing.setup_tracing(app) is None
    assert tracing._provider is None


def test_setup_tracing_initializes_provider_and_instrumentation(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(tracing.settings, "TRACING_ENABLED", True)
    monkeypatch.setattr(tracing.settings, "OTEL_SERVICE_NAME", "test-service")
    monkeypatch.setattr(tracing.settings, "ENVIRONMENT", "testing")
    monkeypatch.setattr(
        tracing.settings,
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://collector:4318",
    )
    monkeypatch.setattr(
        tracing.settings,
        "OTEL_EXPORT_TIMEOUT_SECONDS",
        3.0,
    )
    monkeypatch.setattr(
        tracing.settings,
        "OTEL_TRACE_SAMPLE_RATIO",
        0.5,
    )

    provider = FakeProvider()
    exporter_arguments: dict[str, object] = {}
    instrumentation_calls: list[str] = []

    class ProviderFactory:
        def __new__(cls, **kwargs):
            provider.constructor_kwargs = kwargs
            return provider

    def exporter_factory(**kwargs):
        exporter_arguments.update(kwargs)
        return object()

    monkeypatch.setattr(
        tracing,
        "Resource",
        SimpleNamespace(
            create=lambda attributes: ("resource", attributes),
        ),
    )
    monkeypatch.setattr(
        tracing,
        "TraceIdRatioBased",
        lambda ratio: ("ratio", ratio),
    )
    monkeypatch.setattr(
        tracing,
        "ParentBased",
        lambda sampler: ("parent", sampler),
    )
    monkeypatch.setattr(tracing, "TracerProvider", ProviderFactory)
    monkeypatch.setattr(tracing, "OTLPSpanExporter", exporter_factory)
    monkeypatch.setattr(
        tracing,
        "BatchSpanProcessor",
        lambda exporter: ("processor", exporter),
    )
    monkeypatch.setattr(
        tracing,
        "_instrument_fastapi",
        lambda app, tracer_provider: instrumentation_calls.append("fastapi"),
    )
    monkeypatch.setattr(
        tracing,
        "_instrument_httpx",
        lambda tracer_provider: instrumentation_calls.append("httpx"),
    )
    monkeypatch.setattr(
        tracing,
        "_instrument_redis",
        lambda tracer_provider: instrumentation_calls.append("redis"),
    )
    monkeypatch.setattr(
        tracing,
        "_instrument_sqlalchemy",
        lambda tracer_provider: instrumentation_calls.append("sqlalchemy"),
    )

    app = FastAPI()
    result = tracing.setup_tracing(app)

    assert result is provider
    assert tracing._provider is provider
    assert tracing._instrumented_app is app
    assert exporter_arguments["endpoint"] == ("http://collector:4318/v1/traces")
    assert exporter_arguments["timeout"] == 3.0
    assert instrumentation_calls == [
        "fastapi",
        "httpx",
        "redis",
        "sqlalchemy",
    ]


def test_setup_tracing_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(tracing.settings, "TRACING_ENABLED", True)

    provider = FakeProvider()
    app = FastAPI()

    monkeypatch.setattr(tracing, "_provider", provider)
    monkeypatch.setattr(tracing, "_instrumented_app", app)

    assert tracing.setup_tracing(app) is provider


def test_setup_existing_provider_instruments_new_app(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(tracing.settings, "TRACING_ENABLED", True)

    provider = FakeProvider()

    monkeypatch.setattr(tracing, "_provider", provider)
    monkeypatch.setattr(tracing, "_instrumented_app", None)

    calls: list[tuple[object, object]] = []

    monkeypatch.setattr(
        tracing,
        "_instrument_fastapi",
        lambda app, tracer_provider: calls.append((app, tracer_provider)),
    )

    app = FastAPI()

    assert tracing.setup_tracing(app) is provider
    assert calls == [(app, provider)]
    assert tracing._instrumented_app is app


def test_setup_tracing_failure_degrades_safely(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(tracing.settings, "TRACING_ENABLED", True)

    monkeypatch.setattr(
        tracing,
        "Resource",
        SimpleNamespace(create=lambda attributes: object()),
    )

    def fail_provider(**kwargs):
        raise RuntimeError("tracing initialization failed")

    monkeypatch.setattr(tracing, "TracerProvider", fail_provider)

    assert tracing.setup_tracing(FastAPI()) is None
    assert tracing._provider is None


def test_get_tracer_returns_none_without_provider():
    assert tracing.get_tracer("test") is None


def test_get_tracer_uses_provider(
    monkeypatch: pytest.MonkeyPatch,
):
    provider = FakeProvider()
    monkeypatch.setattr(tracing, "_provider", provider)

    assert tracing.get_tracer("worker") == "tracer:worker"


def test_force_flush_without_provider():
    assert tracing.force_flush_tracing() is True


def test_force_flush_uses_timeout(
    monkeypatch: pytest.MonkeyPatch,
):
    provider = FakeProvider()

    monkeypatch.setattr(tracing, "_provider", provider)
    monkeypatch.setattr(
        tracing.settings,
        "OTEL_EXPORT_TIMEOUT_SECONDS",
        2.5,
    )

    assert tracing.force_flush_tracing() is True
    assert provider.flush_calls == [2500]


def test_force_flush_failure_is_safe(
    monkeypatch: pytest.MonkeyPatch,
):
    class FailingProvider:
        def force_flush(self, timeout_millis: int):
            raise RuntimeError("collector unavailable")

    monkeypatch.setattr(tracing, "_provider", FailingProvider())

    assert tracing.force_flush_tracing() is False


def test_shutdown_flushes_and_resets_provider(
    monkeypatch: pytest.MonkeyPatch,
):
    provider = FakeProvider()

    monkeypatch.setattr(tracing, "_provider", provider)
    monkeypatch.setattr(
        tracing.settings,
        "OTEL_EXPORT_TIMEOUT_SECONDS",
        4.0,
    )

    tracing.shutdown_tracing()

    assert provider.flush_calls == [4000]
    assert provider.shutdown_calls == 1
    assert tracing._provider is None


def test_shutdown_uninstruments_everything(
    monkeypatch: pytest.MonkeyPatch,
):
    provider = FakeProvider()
    app = FastAPI()

    monkeypatch.setattr(tracing, "_provider", provider)
    monkeypatch.setattr(tracing, "_instrumented_app", app)
    monkeypatch.setattr(tracing, "_httpx_instrumented", True)
    monkeypatch.setattr(tracing, "_redis_instrumented", True)
    monkeypatch.setattr(tracing, "_sqlalchemy_instrumented", True)

    calls: list[str] = []

    class FakeFastAPIInstrumentor:
        @staticmethod
        def uninstrument_app(target):
            calls.append("fastapi")

    class FakeHTTPXInstrumentor:
        def uninstrument(self):
            calls.append("httpx")

    class FakeRedisInstrumentor:
        def uninstrument(self):
            calls.append("redis")

    class FakeSQLAlchemyInstrumentor:
        def uninstrument(self):
            calls.append("sqlalchemy")

    monkeypatch.setattr(
        tracing,
        "FastAPIInstrumentor",
        FakeFastAPIInstrumentor,
    )
    monkeypatch.setattr(
        tracing,
        "HTTPXClientInstrumentor",
        FakeHTTPXInstrumentor,
    )
    monkeypatch.setattr(
        tracing,
        "RedisInstrumentor",
        FakeRedisInstrumentor,
    )
    monkeypatch.setattr(
        tracing,
        "SQLAlchemyInstrumentor",
        FakeSQLAlchemyInstrumentor,
    )

    tracing.shutdown_tracing()

    assert calls == ["fastapi", "httpx", "redis", "sqlalchemy"]
    assert tracing._httpx_instrumented is False
    assert tracing._redis_instrumented is False
    assert tracing._sqlalchemy_instrumented is False


def test_shutdown_instrumentor_failures_are_safe(
    monkeypatch: pytest.MonkeyPatch,
):
    provider = FakeProvider()

    monkeypatch.setattr(tracing, "_provider", provider)
    monkeypatch.setattr(tracing, "_instrumented_app", FastAPI())
    monkeypatch.setattr(tracing, "_httpx_instrumented", True)
    monkeypatch.setattr(tracing, "_redis_instrumented", True)
    monkeypatch.setattr(tracing, "_sqlalchemy_instrumented", True)

    class FailingFastAPIInstrumentor:
        @staticmethod
        def uninstrument_app(app):
            raise RuntimeError("failure")

    class FailingInstrumentor:
        def uninstrument(self):
            raise RuntimeError("failure")

    monkeypatch.setattr(
        tracing,
        "FastAPIInstrumentor",
        FailingFastAPIInstrumentor,
    )
    monkeypatch.setattr(
        tracing,
        "HTTPXClientInstrumentor",
        FailingInstrumentor,
    )
    monkeypatch.setattr(
        tracing,
        "RedisInstrumentor",
        FailingInstrumentor,
    )
    monkeypatch.setattr(
        tracing,
        "SQLAlchemyInstrumentor",
        FailingInstrumentor,
    )

    tracing.shutdown_tracing()

    assert tracing._provider is None
    assert tracing._httpx_instrumented is False
    assert tracing._redis_instrumented is False
    assert tracing._sqlalchemy_instrumented is False


def test_shutdown_provider_failures_are_safe(
    monkeypatch: pytest.MonkeyPatch,
):
    class FailingProvider:
        def force_flush(self, timeout_millis: int):
            raise RuntimeError("flush failure")

        def shutdown(self):
            raise RuntimeError("shutdown failure")

    monkeypatch.setattr(tracing, "_provider", FailingProvider())

    tracing.shutdown_tracing()

    assert tracing._provider is None


def test_tracing_config_rejects_invalid_endpoint():
    with pytest.raises(
        ValidationError,
        match="OTEL_EXPORTER_OTLP_ENDPOINT",
    ):
        Settings(
            **_settings_kwargs(),
            TRACING_ENABLED=True,
            OTEL_EXPORTER_OTLP_ENDPOINT="collector:4318",
        )


def test_tracing_config_rejects_credentials_in_endpoint():
    with pytest.raises(
        ValidationError,
        match="embedded credentials",
    ):
        Settings(
            **_settings_kwargs(),
            TRACING_ENABLED=True,
            OTEL_EXPORTER_OTLP_ENDPOINT=(
                "https://user:password@collector.example:4318"
            ),
        )


def test_tracing_config_rejects_empty_service_name():
    with pytest.raises(
        ValidationError,
        match="OTEL_SERVICE_NAME cannot be empty",
    ):
        Settings(
            **_settings_kwargs(),
            TRACING_ENABLED=True,
            OTEL_SERVICE_NAME="   ",
        )


def test_tracing_config_rejects_long_service_name():
    with pytest.raises(
        ValidationError,
        match="must not exceed 128 characters",
    ):
        Settings(
            **_settings_kwargs(),
            TRACING_ENABLED=True,
            OTEL_SERVICE_NAME="x" * 129,
        )


def test_tracing_config_accepts_valid_values():
    configured = Settings(
        **_settings_kwargs(),
        TRACING_ENABLED=True,
        OTEL_SERVICE_NAME="api-test",
        OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318",
        OTEL_EXPORT_TIMEOUT_SECONDS=2.0,
        OTEL_TRACE_SAMPLE_RATIO=0.25,
    )

    assert configured.TRACING_ENABLED is True
    assert configured.OTEL_SERVICE_NAME == "api-test"
    assert configured.OTEL_EXPORT_TIMEOUT_SECONDS == 2.0
    assert configured.OTEL_TRACE_SAMPLE_RATIO == 0.25


def test_capture_trace_context_rejects_oversized_traceparent(
    monkeypatch: pytest.MonkeyPatch,
):
    class FakePropagator:
        def inject(self, carrier):
            carrier["traceparent"] = "x" * 257
            carrier["tracestate"] = "vendor=value"

    monkeypatch.setattr(
        tracing,
        "_trace_context_propagator",
        FakePropagator(),
    )

    traceparent, tracestate = tracing.capture_trace_context()

    assert traceparent is None
    assert tracestate is None


def test_capture_trace_context_rejects_oversized_tracestate(
    monkeypatch: pytest.MonkeyPatch,
):
    class FakePropagator:
        def inject(self, carrier):
            carrier["traceparent"] = (
                "00-11111111111111111111111111111111-2222222222222222-01"
            )
            carrier["tracestate"] = "x" * 513

    monkeypatch.setattr(
        tracing,
        "_trace_context_propagator",
        FakePropagator(),
    )

    traceparent, tracestate = tracing.capture_trace_context()

    assert traceparent is not None
    assert tracestate is None


def test_extract_trace_context_ignores_oversized_values(
    monkeypatch: pytest.MonkeyPatch,
):
    captured_carrier: dict[str, str] = {}

    class FakePropagator:
        def extract(self, carrier):
            captured_carrier.update(carrier)
            return Context()

    monkeypatch.setattr(
        tracing,
        "_trace_context_propagator",
        FakePropagator(),
    )

    tracing.extract_trace_context(
        "x" * 257,
        "y" * 513,
    )

    assert captured_carrier == {}


def test_extract_trace_context_failure_returns_empty_context(
    monkeypatch: pytest.MonkeyPatch,
):
    class FailingPropagator:
        def extract(self, carrier):
            raise ValueError("invalid trace context")

    monkeypatch.setattr(
        tracing,
        "_trace_context_propagator",
        FailingPropagator(),
    )

    context = tracing.extract_trace_context(
        "00-11111111111111111111111111111111-2222222222222222-01",
        None,
    )

    assert isinstance(context, Context)
