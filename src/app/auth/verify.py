import jwt

from app.auth.jwt import ALGORITHM, SECRET_KEY


def verify_token(token: str):
    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
    )