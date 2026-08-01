from app.auth.decode_token import decode_token


def get_user_from_token(
    token: str,
):
    payload = decode_token(token)

    return payload.sub