from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status

from app.auth.decode_token import decode_token
from app.auth.dependencies import get_current_token
from app.auth.token_payload import TokenPayload
from app.core.config import settings


def require_recent_authentication(
    token: str = Depends(get_current_token),
) -> TokenPayload:
    payload = decode_token(token)
    if payload.auth_time is None or not ({"pwd", "oidc"} & set(payload.amr)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recent authentication required",
        )

    authenticated_at = datetime.fromtimestamp(payload.auth_time, tz=UTC)
    now = datetime.now(UTC)
    if authenticated_at > now + timedelta(
        seconds=30
    ) or now - authenticated_at > timedelta(
        minutes=settings.OIDC_RECENT_AUTH_MAX_AGE_MINUTES
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recent authentication required",
        )
    return payload
