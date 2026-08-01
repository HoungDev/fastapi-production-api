from fastapi import APIRouter

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)
from fastapi import Depends

from app.auth.current_user import get_current_user


@router.get("/me")
def get_me(
    current_user=Depends(get_current_user),
):
    return current_user