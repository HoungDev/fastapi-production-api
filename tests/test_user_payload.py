from app.auth.token_payload import TokenPayload


def test_user_payload():
    payload = TokenPayload(
        sub="houngdev",
    )

    assert payload.sub == "houngdev"