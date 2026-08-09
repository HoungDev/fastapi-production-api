from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.db.dependency import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse

router = APIRouter(
    prefix="/register",
    tags=["Authentication"],
)


@router.post("/", response_model=UserResponse)
def register(
    user: UserCreate,
    db: Session = Depends(get_db),
):
    hashed_password = hash_password(user.password)

    db_user = User(
        username=user.username,
        password=hashed_password,
        email=user.email,
    )

    try:
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email is already registered",
        ) from exc
    except Exception:
        db.rollback()
        raise

    return db_user
