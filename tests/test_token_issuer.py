from app.auth.jwt import create_access_token
from app.auth.verify import verify_token


def test_token_issuer():
    token = create_access_token(
        {
            "sub": "houngdev",
            "iss": "fastapi-production-api",
        }
    )

    payload = verify_token(token)

    assert payload["iss"] == "fastapi-production-api"
