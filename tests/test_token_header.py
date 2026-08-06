from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_missing_bearer_token_header():
    response = client.get(
        "/me/",
        headers={
            "Authorization": "Token abc123",
        },
    )

    assert response.status_code == 401
