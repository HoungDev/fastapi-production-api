from fastapi import APIRouter, Cookie, Depends, Query
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.current_user import get_current_user
from app.auth.login import get_device_name
from app.auth.recent_auth import require_recent_authentication
from app.auth.token_payload import TokenPayload
from app.core.config import settings
from app.db.dependency import get_db
from app.models.user import User
from app.schemas.mfa import MFAChallengeResponse
from app.schemas.oidc import (
    ExternalIdentityResponse,
    OIDCLinkResponse,
    OIDCMessageResponse,
)
from app.schemas.token import Token
from app.services.oidc import (
    BROWSER_COOKIE_NAME,
    begin_oidc_authorization,
    complete_oidc_authorization,
    list_external_identities,
    unlink_external_identity,
)
from app.services.oidc_provider import OIDCProviderClient, get_oidc_provider_client

router = APIRouter(prefix="/auth/oidc", tags=["OpenID Connect"])


def _redirect_with_binding(url: str, binding: str, expires_in: int) -> RedirectResponse:
    response = RedirectResponse(url=url, status_code=303)
    response.set_cookie(
        BROWSER_COOKIE_NAME,
        binding,
        max_age=expires_in,
        httponly=True,
        secure=settings.ENVIRONMENT.lower() == "production",
        samesite="lax",
        path="/auth/oidc/callback",
    )
    return response


@router.get("/authorize", response_class=RedirectResponse)
def authorize_login(
    db: Session = Depends(get_db),
    provider: OIDCProviderClient = Depends(get_oidc_provider_client),
    device_name: str = Depends(get_device_name),
):
    start = begin_oidc_authorization(
        db,
        provider,
        intent="login",
        device_name=device_name,
    )
    return _redirect_with_binding(
        start.authorization_url,
        start.browser_binding,
        start.expires_in,
    )


@router.post("/link/authorize", response_class=RedirectResponse)
def authorize_link(
    current_user: User = Depends(get_current_user),
    recent_auth: TokenPayload = Depends(require_recent_authentication),
    db: Session = Depends(get_db),
    provider: OIDCProviderClient = Depends(get_oidc_provider_client),
    device_name: str = Depends(get_device_name),
):
    start = begin_oidc_authorization(
        db,
        provider,
        intent="link",
        user_id=current_user.id,
        device_name=device_name,
    )
    return _redirect_with_binding(
        start.authorization_url,
        start.browser_binding,
        start.expires_in,
    )


@router.get(
    "/callback",
    response_model=Token | MFAChallengeResponse | OIDCLinkResponse,
)
def callback(
    state: str | None = Query(default=None, min_length=32, max_length=512),
    code: str | None = Query(default=None, min_length=1, max_length=4096),
    _error: str | None = Query(default=None, alias="error", max_length=255),
    browser_binding: str | None = Cookie(
        default=None,
        alias=BROWSER_COOKIE_NAME,
    ),
    db: Session = Depends(get_db),
    provider: OIDCProviderClient = Depends(get_oidc_provider_client),
):
    result = complete_oidc_authorization(
        state or "",
        code or "",
        browser_binding,
        db,
        provider,
    )
    response = JSONResponse(result.response.model_dump(mode="json"))
    response.delete_cookie(
        BROWSER_COOKIE_NAME,
        path="/auth/oidc/callback",
        secure=settings.ENVIRONMENT.lower() == "production",
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/identities", response_model=list[ExternalIdentityResponse])
def identities(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_external_identities(current_user.id, db)


@router.delete(
    "/identities/{identity_id}",
    response_model=OIDCMessageResponse,
)
def unlink_identity(
    identity_id: int,
    current_user: User = Depends(get_current_user),
    recent_auth: TokenPayload = Depends(require_recent_authentication),
    db: Session = Depends(get_db),
):
    unlink_external_identity(identity_id, current_user.id, db)
    return OIDCMessageResponse(message="External identity unlinked")
