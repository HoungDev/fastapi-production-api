from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.auth.jwt import create_access_token
from app.schemas import Token

router = APIRouter(
    prefix="/login",
    tags=["Authentication"],
)


@router.post("/", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    access_token = create_access_token(
        {"sub": form_data.username}
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
    )