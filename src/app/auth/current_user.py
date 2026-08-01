from fastapi import Depends, HTTPException, status

from app.auth.decode_token import decode_token
from app.auth.dependencies import get_current_token


def get_current_user(
    token: str = Depends(get_current_token),
):
    payload = decode_token(token)

    if not payload.sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    return payload