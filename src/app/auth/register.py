from fastapi import APIRouter

router = APIRouter(
    prefix="/register",
    tags=["Authentication"],
)
from app.schemas import UserCreate


@router.post("/")
def register(
    user: UserCreate,
):
    return user