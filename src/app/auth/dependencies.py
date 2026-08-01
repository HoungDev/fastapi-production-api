from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


def get_current_token(
    token: str = Depends(oauth2_scheme),
):
    return token