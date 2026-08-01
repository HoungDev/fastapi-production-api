from fastapi import Depends

from app.auth.dependencies import get_current_token


def get_current_user(
    token: str = Depends(get_current_token),
):
    return {
        "token": token,
    }