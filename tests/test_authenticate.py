from app.auth.authenticate import authenticate_user
from app.auth.security import hash_password


def test_authenticate_user():
    password = "secret123"
    hashed_password = hash_password(password)

    assert (
        authenticate_user(
            password,
            hashed_password,
        )
        is True
    )


def test_authenticate_user_rejects_malformed_hash():
    assert (
        authenticate_user(
            "secret123",
            "not-a-bcrypt-hash",
        )
        is False
    )
