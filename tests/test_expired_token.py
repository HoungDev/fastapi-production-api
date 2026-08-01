from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.auth.verify import verify_token
from app.auth.jwt import SECRET_KEY, ALGORITHM


def test_expired_token():
    payload = {
        "sub": "houngdev",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
    }

    token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    with pytest.raises(Exception):
        verify_token(token)