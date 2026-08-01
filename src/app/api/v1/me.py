from fastapi import APIRouter, Depends

from app.auth.current_user import get_current_user

router = APIRouter(
    prefix="/me",
    tags=["Current User"],
)


@router.get("/")
def read_current_user(
    current_user=Depends(get_current_user),
):
    return current_user