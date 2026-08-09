from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from fastapi_production_api import __version__

client = TestClient(app)


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_liveness_does_not_require_database():
    with patch("app.api.v1.health.engine.connect") as connect:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    connect.assert_not_called()


def test_readiness_checks_database():
    context_manager = MagicMock()
    connection = context_manager.__enter__.return_value

    with patch(
        "app.api.v1.health.engine.connect",
        return_value=context_manager,
    ):
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok"},
    }
    connection.execute.assert_called_once()


def test_readiness_returns_503_when_database_is_unavailable():
    with patch(
        "app.api.v1.health.engine.connect",
        side_effect=RuntimeError("database unavailable"),
    ):
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "checks": {"database": "unavailable"},
    }


def test_redis_readiness_reports_each_required_dependency(monkeypatch):
    context_manager = MagicMock()
    redis_client = MagicMock()
    redis_client.ping = AsyncMock(return_value=True)
    monkeypatch.setattr("app.api.v1.health.settings.RATE_LIMIT_BACKEND", "redis")

    with (
        patch(
            "app.api.v1.health.engine.connect",
            return_value=context_manager,
        ),
        patch("app.api.v1.health.get_redis_client", return_value=redis_client),
    ):
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "redis": "ok"},
    }


def test_redis_outage_fails_readiness_without_affecting_liveness(monkeypatch):
    context_manager = MagicMock()
    redis_client = MagicMock()
    redis_client.ping = AsyncMock(side_effect=OSError("redis unavailable"))
    monkeypatch.setattr("app.api.v1.health.settings.RATE_LIMIT_BACKEND", "redis")

    with (
        patch(
            "app.api.v1.health.engine.connect",
            return_value=context_manager,
        ),
        patch("app.api.v1.health.get_redis_client", return_value=redis_client),
    ):
        readiness_response = client.get("/health/ready")
        liveness_response = client.get("/health/live")

    assert readiness_response.status_code == 503
    assert readiness_response.json() == {
        "status": "error",
        "checks": {"database": "ok", "redis": "unavailable"},
    }
    assert liveness_response.status_code == 200


def test_legacy_database_health_alias_preserves_response_shape():
    context_manager = MagicMock()

    with patch(
        "app.api.v1.health.engine.connect",
        return_value=context_manager,
    ):
        response = client.get("/health/db")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "connected",
    }


def test_legacy_database_health_alias_reports_unavailable_database():
    with patch(
        "app.api.v1.health.engine.connect",
        side_effect=OSError("database unavailable"),
    ):
        response = client.get("/health/db")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "database": "disconnected",
    }


def test_root_exposes_package_version():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["version"] == __version__


def test_security_headers_allow_api_documentation_assets():
    response = client.get("/docs")

    assert response.status_code == 200
    policy = response.headers["content-security-policy"]
    assert "https://cdn.jsdelivr.net" in policy
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["permissions-policy"]
