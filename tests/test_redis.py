import asyncio
from unittest.mock import AsyncMock

from pydantic import SecretStr

from app.core import redis as redis_core


def test_redis_client_is_pooled_and_closed(monkeypatch):
    fake_client = AsyncMock()

    def factory(*args, **kwargs):
        return fake_client

    monkeypatch.setattr(redis_core.Redis, "from_url", factory)
    monkeypatch.setattr(redis_core, "_redis_client", None)
    monkeypatch.setattr(
        redis_core.settings,
        "REDIS_URL",
        SecretStr("redis://user:secret@localhost:6379/0"),
    )

    first = redis_core.get_redis_client()
    second = redis_core.get_redis_client()
    asyncio.run(redis_core.close_redis_client())

    assert first is fake_client
    assert second is fake_client
    fake_client.aclose.assert_awaited_once()
    assert redis_core._redis_client is None
