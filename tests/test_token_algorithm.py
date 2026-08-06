from app.auth.jwt import ALGORITHM


def test_token_algorithm():
    assert ALGORITHM == "HS256"
