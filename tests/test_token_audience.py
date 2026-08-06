from app.auth.jwt import create_access_token
from app.auth.verify import verify_token


def test_token_audience():
    token = create_access_token(
        {
            "sub": "houngdev",
            "aud": "fastapi-client",
        }
    )

    payload = verify_token(token)

    assert payload["aud"] == "fastapi-client"
