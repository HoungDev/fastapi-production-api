from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.current_user import get_current_user
from app.auth.permissions import require_admin
from app.db.dependency import get_db
from app.models.user import User
from app.schemas.user import UserAdminResponse, UserRoleUpdate, UserStatusUpdate
from app.services.sessions import (
    ACCOUNT_DISABLED_REVOCATION_REASON,
    revoke_all_user_sessions,
)

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)


@router.get("/test")
def admin_test(
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)

    return {
        "message": "Welcome admin",
        "username": current_user.username,
        "role": current_user.role,
    }


@router.get(
    "/users",
    response_model=list[UserAdminResponse],
)
def list_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    return db.query(User).all()


@router.get(
    "/users/{user_id}",
    response_model=UserAdminResponse,
)
def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user


@router.patch(
    "/users/{user_id}/role",
    response_model=UserAdminResponse,
)
def update_user_role(
    user_id: int,
    data: UserRoleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.role = data.role

    db.commit()
    db.refresh(user)

    return user


@router.patch(
    "/users/{user_id}/status",
    response_model=UserAdminResponse,
)
def update_user_status(
    user_id: int,
    data: UserStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    try:
        user.is_active = data.is_active
        if data.is_active:
            db.commit()
        else:
            revoke_all_user_sessions(
                user.id,
                db,
                reason=ACCOUNT_DISABLED_REVOCATION_REASON,
            )
        db.refresh(user)
    except Exception:
        db.rollback()
        raise

    return user


@router.delete(
    "/users/{user_id}",
)
def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    db.delete(user)
    db.commit()

    return {"message": "User deleted successfully"}
