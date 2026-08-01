from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

router = APIRouter(
    prefix="/login",
    tags=["Authentication"],
)


@router.post("/")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    return {
        "username": form_data.username,
    }