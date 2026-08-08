from fastapi import APIRouter, Depends

from app.auth.current_user import get_current_user
from app.models.user import User

router = APIRouter(
    tags=["Authentication"],
)


@router.get(
    "/me/",
)
def get_me(
    current_user: User = Depends(get_current_user),
):
    return {
        "sub": current_user.username,
    }
