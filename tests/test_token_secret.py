from app.auth.jwt import SECRET_KEY


def test_token_secret_exists():
    assert SECRET_KEY is not None
    assert len(SECRET_KEY) > 0
