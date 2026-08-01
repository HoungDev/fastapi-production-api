from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["Users"])
from app.schemas import UserCreate


@router.post("/")
def create_user(user: UserCreate):
    return user