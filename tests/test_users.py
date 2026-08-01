from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_create_user():
    response = client.post(
        "/users/",
        json={
            "username": "houngdev",
            "password": "secret123",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["username"] == "houngdev"