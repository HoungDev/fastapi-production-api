from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth.jwt import create_access_token
from app.auth.refresh_token import (
    create_refresh_token,
    hash_refresh_token,
)
from app.auth.security import verify_password
from app.db.dependency import get_db
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas import Token

router = APIRouter(
    prefix="/login",
    tags=["Authentication"],
)


@router.post("/", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == form_data.username).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    if not verify_password(
        form_data.password,
        user.password,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    access_token = create_access_token({"sub": user.username})

    refresh_token, expires_at = create_refresh_token()

    db_refresh_token = RefreshToken(
        user_id=user.id,
        token=hash_refresh_token(refresh_token),
        expires_at=expires_at,
    )

    try:
        db.add(db_refresh_token)
        db.commit()

    except Exception:
        db.rollback()
        raise

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )
