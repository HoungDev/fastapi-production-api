from datetime import datetime, timezone

from app.auth.jwt import create_access_token
from app.auth.verify import verify_token


def test_token_has_expiration():
    token = create_access_token({"sub": "houngdev"})

    payload = verify_token(token)

    assert "exp" in payload
    assert payload["exp"] > datetime.now(timezone.utc).timestamp()
