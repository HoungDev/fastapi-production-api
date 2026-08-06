from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.main import app

client = TestClient(app)


def test_missing_subject():
    token = create_access_token({})

    response = client.get(
        "/me/",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 401
