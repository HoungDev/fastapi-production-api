from app.auth.get_current_user import get_user_from_token
from app.auth.jwt import create_access_token


def test_get_user_from_token():
    token = create_access_token(
        {"sub": "houngdev"},
    )

    username = get_user_from_token(token)

    assert username == "houngdev"
