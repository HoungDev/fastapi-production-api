from fastapi.testclient import TestClient

from app.main import app
from app.auth.jwt import create_access_token


client = TestClient(app)


def test_protected_route():
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