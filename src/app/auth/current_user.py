from fastapi import Depends

from app.auth.decode_token import decode_token
from app.auth.dependencies import get_current_token


def get_current_user(
    token: str = Depends(get_current_token),
):
    return decode_token(token)