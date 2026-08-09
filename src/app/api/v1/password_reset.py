import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.dependency import get_db
from app.schemas.password_reset import (
    PasswordResetAccepted,
    PasswordResetConfirm,
    PasswordResetRequest,
)
from app.services.email_delivery import EmailSender, get_email_sender
from app.services.password_reset import (
    confirm_password_reset,
    issue_password_reset_token,
)

logger = logging.getLogger("fastapi-production-api")
ACCEPTED_MESSAGE = "If the address is eligible, a password reset email will be sent"

router = APIRouter(
    prefix="/auth/password-reset",
    tags=["Authentication"],
)


@router.post(
    "/request",
    response_model=PasswordResetAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_password_reset(
    data: PasswordResetRequest,
    db: Session = Depends(get_db),
    sender: EmailSender | None = Depends(get_email_sender),
) -> PasswordResetAccepted:
    if sender is None and settings.EMAIL_DELIVERY_MODE != "outbox":
        return PasswordResetAccepted(message=ACCEPTED_MESSAGE)

    delivery = issue_password_reset_token(str(data.email), db)
    if delivery is not None and sender is not None:
        recipient, raw_token = delivery
        try:
            sender.send_password_reset(recipient, raw_token)
        except Exception:
            logger.error("Password reset delivery failed")

    return PasswordResetAccepted(message=ACCEPTED_MESSAGE)


@router.post(
    "/confirm",
    response_model=PasswordResetAccepted,
)
def confirm_reset(
    data: PasswordResetConfirm,
    db: Session = Depends(get_db),
) -> PasswordResetAccepted:
    confirm_password_reset(data.token, data.new_password, db)
    return PasswordResetAccepted(message="Password reset successfully")
