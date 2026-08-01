from app.auth.jwt import create_access_token
from app.auth.verify import verify_token


def test_token_claims():
    token = create_access_token(
        {
            "sub": "houngdev",
            "role": "user",
        }
    )

    payload = verify_token(token)

    assert payload["sub"] == "houngdev"
    assert payload["role"] == "user"