from app.auth.authenticate import authenticate_user
from app.auth.security import hash_password


def test_authenticate_user():
    password = "secret123"
    hashed_password = hash_password(password)

    assert authenticate_user(
        password,
        hashed_password,
    ) is True