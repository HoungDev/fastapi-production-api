from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.current_user import get_current_user
from app.auth.refresh import (
    refresh_access_token,
    revoke_refresh_token,
)
from app.db.dependency import get_db
from app.models.user import User
from app.schemas.refresh_token import RefreshTokenRequest
from app.schemas.token import Token
from app.schemas.user import UserResponse


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.post(
    "/refresh",
    response_model=Token,
)
def refresh(
    data: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    access_token = refresh_access_token(
        data.refresh_token,
        db,
    )

    return Token(
        access_token=access_token,
        refresh_token=data.refresh_token,
        token_type="bearer",
    )


@router.post(
    "/logout",
)
def logout(
    data: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    revoke_refresh_token(
        data.refresh_token,
        db,
    )

    return {
        "message": "Logged out successfully"
    }