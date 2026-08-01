from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_create_user():
    response = client.post(
        "/users/",
        json={
            "username": "houngdev"
        },
    )

    assert response.status_code == 200
    assert response.json() == {
    "success": True,
    "data": {
        "username": "houngdev",
    },
}