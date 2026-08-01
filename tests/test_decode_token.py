from app.auth.decode_token import decode_token
from app.auth.jwt import create_access_token


def test_decode_token():
    token = create_access_token(
        {"sub": "houngdev"},
    )

    payload = decode_token(token)

    assert payload.sub == "houngdev"