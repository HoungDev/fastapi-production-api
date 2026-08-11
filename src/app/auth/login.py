from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth.refresh_token import normalize_device_name
from app.auth.security import verify_password
from app.db.dependency import get_db
from app.models.user import User
from app.schemas import Token
from app.schemas.mfa import MFAChallengeResponse
from app.services.mfa import issue_mfa_login_challenge
from app.services.session_issuance import prepare_session_tokens

router = APIRouter(
    prefix="/login",
    tags=["Authentication"],
)


def get_device_name(request: Request) -> str:
    return normalize_device_name(
        request.headers.get("X-Device-Name"),
        request.headers.get("User-Agent"),
    )


@router.post("/", response_model=Token | MFAChallengeResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    device_name: str = Depends(get_device_name),
):
    user = db.query(User).filter(User.username == form_data.username).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    if not user.password_login_enabled or not verify_password(
        form_data.password,
        user.password,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    if user.mfa_enabled_at is not None:
        return issue_mfa_login_challenge(user, device_name, db)

    try:
        tokens = prepare_session_tokens(
            user,
            device_name,
            db,
            authentication_methods=["pwd"],
        )
        db.commit()

    except Exception:
        db.rollback()
        raise

    return tokens
