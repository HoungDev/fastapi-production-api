import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.dependency import get_db
from app.schemas.email_verification import (
    EmailVerificationAccepted,
    EmailVerificationConfirm,
    EmailVerificationRequest,
)
from app.services.email_delivery import EmailSender, get_email_sender
from app.services.email_verification import (
    confirm_email_verification,
    issue_email_verification_token,
)

logger = logging.getLogger("fastapi-production-api")
ACCEPTED_MESSAGE = (
    "If the address is eligible, a verification email will be sent shortly"
)

router = APIRouter(
    prefix="/auth/email-verification",
    tags=["Authentication"],
)


@router.post(
    "/request",
    response_model=EmailVerificationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_email_verification(
    data: EmailVerificationRequest,
    db: Session = Depends(get_db),
    sender: EmailSender | None = Depends(get_email_sender),
) -> EmailVerificationAccepted:
    if sender is None:
        return EmailVerificationAccepted(message=ACCEPTED_MESSAGE)

    delivery = issue_email_verification_token(str(data.email), db)
    if delivery is not None:
        recipient, raw_token = delivery
        try:
            sender.send_verification(recipient, raw_token)
        except Exception:
            logger.error("Email verification delivery failed")

    return EmailVerificationAccepted(message=ACCEPTED_MESSAGE)


@router.post(
    "/confirm",
    response_model=EmailVerificationAccepted,
)
def confirm_verification(
    data: EmailVerificationConfirm,
    db: Session = Depends(get_db),
) -> EmailVerificationAccepted:
    confirm_email_verification(data.token, db)
    return EmailVerificationAccepted(message="Email address verified")
