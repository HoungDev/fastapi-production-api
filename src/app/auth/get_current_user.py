from fastapi import Depends

from app.auth.decode_token import decode_token
from app.auth.dependencies import oauth2_scheme


def get_user_from_token(
    token: str = Depends(oauth2_scheme),
):
    payload = decode_token(token)

    return payload.sub