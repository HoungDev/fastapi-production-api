from app.auth.jwt import create_access_token
from app.auth.verify import verify_token


def test_token_role():
    token = create_access_token(
        {
            "sub": "houngdev",
            "role": "admin",
        }
    )

    payload = verify_token(token)

    assert payload["role"] == "admin"
