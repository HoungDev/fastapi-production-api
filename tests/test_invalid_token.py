from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_invalid_token():
    response = client.get(
        "/me/",
        headers={
            "Authorization": "Bearer invalid-token",
        },
    )

    assert response.status_code == 401
