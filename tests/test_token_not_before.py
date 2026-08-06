from datetime import datetime, timedelta, timezone

import jwt

from app.auth.jwt import ALGORITHM, SECRET_KEY
from app.auth.verify import verify_token


def test_token_not_before():
    future_time = datetime.now(timezone.utc) + timedelta(minutes=5)

    token = jwt.encode(
        {
            "sub": "houngdev",
            "nbf": future_time,
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    try:
        verify_token(token)
        assert False, "Token should not be valid before nbf time"

    except Exception:
        assert True
