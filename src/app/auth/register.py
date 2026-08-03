from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.dependency import get_db
from app.models.user import User
from app.schemas import UserCreate, UserResponse
from app.core.security import hash_password
router = APIRouter(
    prefix="/register",
    tags=["Authentication"],
)
from app.schemas import UserCreate


@router.post("/", response_model=UserResponse)
def register(
    user: UserCreate,
    db: Session = Depends(get_db),
):
    db_user = User(
        username=user.username,
        password=hash_password(user.password)
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user