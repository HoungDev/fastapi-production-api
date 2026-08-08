from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_register():
    username = f"newuser_{uuid4().hex[:8]}"

    response = client.post(
        "/register/",
        json={
            "username": username,
            "password": "secret123",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["username"] == username
    assert data["role"] == "user"
    assert "id" in data
    assert "password" not in data
