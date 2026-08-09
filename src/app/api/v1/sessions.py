from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.current_user import get_current_user
from app.db.dependency import get_db
from app.models.user import User
from app.schemas.session import DeviceSession, SessionRevocationResponse
from app.services.sessions import (
    list_active_sessions,
    revoke_all_user_sessions,
    revoke_session_family,
)

router = APIRouter(
    prefix="/auth/sessions",
    tags=["Authentication"],
)


@router.get("", response_model=list[DeviceSession])
def get_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DeviceSession]:
    return list_active_sessions(current_user.id, db)


@router.delete("/{session_id}", response_model=SessionRevocationResponse)
def revoke_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionRevocationResponse:
    revoke_session_family(current_user.id, str(session_id), db)
    return SessionRevocationResponse(message="Session revoked")


@router.delete("", response_model=SessionRevocationResponse)
def revoke_all_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionRevocationResponse:
    revoke_all_user_sessions(current_user.id, db)
    return SessionRevocationResponse(message="All sessions revoked")
