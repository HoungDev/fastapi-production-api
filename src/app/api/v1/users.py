from fastapi import APIRouter

from app.schemas import UserCreate
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])
from app.schemas import UserCreate


service = UserService()


@router.post("/")
def create_user(user: UserCreate):
    return service.create_user(user)
from app.services.user_service import UserService