from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.current_user import get_current_user
from app.db.dependency import get_db
from app.models.user import User
from app.schemas.mfa import (
    MFACodeRequest,
    MFADisableRequest,
    MFAEnrollmentResponse,
    MFAMessageResponse,
    MFAPasswordRequest,
    MFARecoveryCodesResponse,
    MFARegenerateRequest,
    MFAStatusResponse,
    MFAVerifyChallengeRequest,
)
from app.schemas.token import Token
from app.services.mfa import (
    begin_totp_enrollment,
    confirm_totp_enrollment,
    disable_mfa,
    get_mfa_status,
    regenerate_recovery_codes,
    verify_mfa_login_challenge,
)

router = APIRouter(prefix="/auth/mfa", tags=["Multi-factor authentication"])


@router.get("/status", response_model=MFAStatusResponse)
def status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_mfa_status(current_user.id, db)


@router.post("/totp/enroll", response_model=MFAEnrollmentResponse)
def enroll_totp(
    payload: MFAPasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return begin_totp_enrollment(current_user.id, payload.password, db)


@router.post("/totp/confirm", response_model=MFARecoveryCodesResponse)
def confirm_totp(
    payload: MFACodeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return confirm_totp_enrollment(current_user.id, payload.code, db)


@router.post(
    "/recovery-codes/regenerate",
    response_model=MFARecoveryCodesResponse,
)
def regenerate_codes(
    payload: MFARegenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return regenerate_recovery_codes(
        current_user.id,
        payload.password,
        payload.code,
        db,
    )


@router.post("/disable", response_model=MFAMessageResponse)
def disable(
    payload: MFADisableRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    disable_mfa(current_user.id, payload.password, payload.code, db)
    return MFAMessageResponse(message="MFA disabled")


@router.post("/challenge/verify", response_model=Token)
def verify_challenge(
    payload: MFAVerifyChallengeRequest,
    db: Session = Depends(get_db),
):
    return verify_mfa_login_challenge(payload.challenge_token, payload.code, db)
