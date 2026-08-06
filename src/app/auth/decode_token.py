from fastapi import HTTPException, status

from app.auth.token_payload import TokenPayload
from app.auth.verify import verify_token


def decode_token(
    token: str,
) -> TokenPayload:
    payload = verify_token(token)

    if "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    return TokenPayload(**payload)
