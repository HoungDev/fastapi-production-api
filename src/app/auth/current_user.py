from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.decode_token import decode_token
from app.auth.dependencies import get_current_token
from app.db.dependency import get_db
from app.models.user import User


def get_current_user(
    token: str = Depends(get_current_token),
    db: Session = Depends(get_db),
):
    payload = decode_token(token)

    if not payload.sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    user = (
        db.query(User)
        .filter(User.username == payload.sub)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user