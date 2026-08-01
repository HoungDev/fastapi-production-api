from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_register():
    response = client.post(
        "/register/",
        json={
            "username": "newuser",
            "password": "secret123",
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "username": "newuser",
        "password": "secret123",
    }