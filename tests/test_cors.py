from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.middlewares.cors import setup_cors


def create_cors_test_client(monkeypatch) -> TestClient:
    monkeypatch.setattr(
        settings,
        "CORS_ORIGINS",
        "https://app.example, https://admin.example",
    )
    test_app = FastAPI()
    setup_cors(test_app)

    @test_app.get("/resource")
    def resource():
        return {"status": "ok"}

    return TestClient(test_app)


def test_cors_allows_configured_origin(monkeypatch):
    client = create_cors_test_client(monkeypatch)

    response = client.options(
        "/resource",
        headers={
            "Origin": "https://app.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ("https://app.example")
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_rejects_unconfigured_origin(monkeypatch):
    client = create_cors_test_client(monkeypatch)

    response = client.options(
        "/resource",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
