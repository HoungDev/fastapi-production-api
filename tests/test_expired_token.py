from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.auth.jwt import ALGORITHM, SECRET_KEY
from app.auth.verify import verify_token


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
