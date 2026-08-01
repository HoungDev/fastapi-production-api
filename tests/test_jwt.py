from app.auth.jwt import create_access_token


def test_create_access_token():
    token = create_access_token({"sub": "houngdev"})

    assert isinstance(token, str)
    assert len(token) > 0