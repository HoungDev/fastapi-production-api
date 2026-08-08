from app.auth.token_payload import TokenPayload


def test_token_payload():
    payload = TokenPayload(
        sub="houngdev",
    )

    assert payload.sub == "houngdev"
