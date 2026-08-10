import os

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)

HTTP_REQUESTS_TOTAL = Counter(
    "fastapi_production_api_http_requests_total",
    "Total HTTP requests handled by the API.",
    ("method", "route", "status_code"),
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "fastapi_production_api_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "fastapi_production_api_http_requests_in_progress",
    "HTTP requests currently being processed.",
    ("method",),
    multiprocess_mode="livesum",
)

RATE_LIMIT_DECISIONS_TOTAL = Counter(
    "fastapi_production_api_rate_limit_decisions_total",
    "Rate-limit decisions made by the API.",
    ("backend", "outcome"),
)

RATE_LIMIT_BACKEND_ERRORS_TOTAL = Counter(
    "fastapi_production_api_rate_limit_backend_errors_total",
    "Rate-limit backend errors by bounded operation category.",
    ("backend", "operation"),
)

OUTBOX_MESSAGES_TOTAL = Counter(
    "fastapi_production_api_outbox_messages_total",
    "Outbox worker message outcomes.",
    ("message_type", "outcome"),
)

OUTBOX_FAILURES_TOTAL = Counter(
    "fastapi_production_api_outbox_failures_total",
    "Outbox worker failures by bounded category.",
    ("category",),
)

OUTBOX_DELIVERY_DURATION_SECONDS = Histogram(
    "fastapi_production_api_outbox_delivery_duration_seconds",
    "Outbox delivery duration in seconds.",
    ("message_type",),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)

OIDC_CACHE_OPERATIONS_TOTAL = Counter(
    "fastapi_production_api_oidc_cache_operations_total",
    "OIDC public-document cache operations.",
    ("document", "outcome"),
)

OIDC_PROVIDER_FETCHES_TOTAL = Counter(
    "fastapi_production_api_oidc_provider_fetches_total",
    "OIDC public-document provider fetch outcomes.",
    ("document", "outcome"),
)

OIDC_PROVIDER_FETCH_DURATION_SECONDS = Histogram(
    "fastapi_production_api_oidc_provider_fetch_duration_seconds",
    "OIDC public-document provider fetch duration in seconds.",
    ("document",),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


def render_metrics() -> tuple[bytes, str]:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        registry = REGISTRY

    return generate_latest(registry), CONTENT_TYPE_LATEST
