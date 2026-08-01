import pytest

from app.auth.decode_token import decode_token


def test_decode_invalid_token():
    with pytest.raises(Exception):
        decode_token("invalid.token.value")