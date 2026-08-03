from fastapi import APIRouter, Depends

from app.auth.current_user import get_current_user
from app.auth.permissions import require_admin
from app.models.user import User


router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)


@router.get("/test")
def admin_test(
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)

    return {
        "message": "Welcome admin",
        "username": current_user.username,
        "role": current_user.role,
    }