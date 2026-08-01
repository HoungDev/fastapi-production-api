from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_me():
    response = client.get(
        "/me/",
        headers={
            "Authorization": "Bearer test-token",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "token": "test-token",
    }