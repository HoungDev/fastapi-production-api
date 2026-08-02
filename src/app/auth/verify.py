import jwt

from fastapi import HTTPException, status

from app.auth.jwt import (
    SECRET_KEY,
    ALGORITHM,
    JWT_AUDIENCE,
    JWT_ISSUER,
)
def verify_token(token: str):
    try:
        return jwt.decode(
    token,
    SECRET_KEY,
    algorithms=[ALGORITHM],
    audience=JWT_AUDIENCE,
    issuer=JWT_ISSUER,
)

    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )