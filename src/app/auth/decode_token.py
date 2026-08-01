from app.auth.verify import verify_token
from app.auth.token_payload import TokenPayload


def decode_token(
    token: str,
) -> TokenPayload:
    payload = verify_token(token)

    return TokenPayload(**payload)