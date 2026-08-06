from fastapi.testclient import TestClient

from app.main import app
from fastapi_production_api import __version__

client = TestClient(app)


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
