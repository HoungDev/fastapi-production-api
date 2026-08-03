from fastapi import HTTPException, status

from app.models.user import User


def require_admin(
    user: User,
):
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return user