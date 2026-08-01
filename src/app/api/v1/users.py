from fastapi import APIRouter, Depends

from app.dependencies.database import get_db
from app.schemas import UserCreate
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])

service = UserService()


@router.post("/")
def create_user(
    user: UserCreate,
    db=Depends(get_db),
):
    return service.create_user(user)