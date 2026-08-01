from app.auth.security import verify_password


def authenticate_user(
    plain_password: str,
    hashed_password: str,
) -> bool:
    return verify_password(
        plain_password,
        hashed_password,
    )