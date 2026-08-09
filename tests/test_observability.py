import json
import logging
import re
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter
from app.main import app

client = TestClient(app)


def test_request_id_is_preserved():
    response = client.get(
        "/health/live",
        headers={"X-Request-ID": "deploy-20260809.1"},
    )

    assert response.headers["X-Request-ID"] == "deploy-20260809.1"


def test_invalid_request_id_is_replaced():
    response = client.get(
        "/health/live",
        headers={"X-Request-ID": "invalid request id"},
    )

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


def test_observability_endpoints_are_not_rate_limited():
    with patch(
        "app.middlewares.rate_limit.rate_limiter.is_allowed",
        return_value=False,
    ):
        liveness_response = client.get("/health/live")
        metrics_response = client.get("/metrics")

    assert liveness_response.status_code == 200
    assert metrics_response.status_code == 200


def test_metrics_include_status_and_route_template():
    client.get("/health/live")
    client.get("/a-path-that-does-not-exist")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert (
        'fastapi_production_api_http_requests_total{method="GET",'
        'route="/health/live",status_code="200"}'
    ) in response.text
    assert 'route="unmatched",status_code="404"' in response.text
    assert "/a-path-that-does-not-exist" not in response.text
    assert "fastapi_production_api_http_request_duration_seconds_bucket" in (
        response.text
    )


def test_json_formatter_emits_correlation_fields():
    record = logging.LogRecord(
        name="fastapi-production-api.request",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="http_request",
        args=(),
        exc_info=None,
    )
    record.request_id = "request-123"
    record.method = "GET"
    record.route = "/health/live"
    record.status_code = 200
    record.duration_ms = 1.25

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "http_request"
    assert payload["request_id"] == "request-123"
    assert payload["method"] == "GET"
    assert payload["route"] == "/health/live"
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 1.25
