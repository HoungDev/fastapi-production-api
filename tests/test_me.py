from app.main import app
from fastapi.testclient import TestClient
from app.auth.jwt import create_access_token


client = TestClient(app)


def test_me():
    token = create_access_token(
        {"sub": "houngdev"},
    )

    response = client.get(
        "/me/",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200
    assert response.json()["sub"] == "houngdev"