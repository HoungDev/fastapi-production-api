import asyncio
import os

import pytest
from redis.asyncio import Redis

from app.middlewares import rate_limit
from app.middlewares.rate_limit import RedisRateLimiter

REDIS_TEST_URL = os.environ.get("REDIS_TEST_URL")
pytestmark = pytest.mark.skipif(
    not REDIS_TEST_URL,
    reason="REDIS_TEST_URL is required for Redis integration tests",
)


def test_multiple_instances_share_atomic_quota_and_bounded_private_keys():
    async def exercise() -> None:
        client = Redis.from_url(REDIS_TEST_URL, decode_responses=False)
        original_get_client = rate_limit.get_redis_client
        rate_limit.get_redis_client = lambda: client
        try:
            await client.flushdb()
            first = RedisRateLimiter(limit=20, window=60, key_secret=b"q" * 48)
            second = RedisRateLimiter(limit=20, window=60, key_secret=b"q" * 48)
            decisions = await asyncio.gather(
                *(first.check("192.0.2.77") for _ in range(15)),
                *(second.check("192.0.2.77") for _ in range(15)),
            )

            assert sum(decision.allowed for decision in decisions) == 20
            independent = await first.check("198.51.100.88")
            assert independent.allowed is True
            keys = await client.keys("*")
            assert len(keys) == 2
            for key in keys:
                decoded_key = key.decode("ascii")
                value = await client.get(key)
                assert "192.0.2.77" not in decoded_key
                assert "198.51.100.88" not in decoded_key
                assert len(decoded_key) <= 128
                assert value is not None and value.isdigit()
                ttl = await client.ttl(key)
                assert 0 < ttl <= 120
        finally:
            rate_limit.get_redis_client = original_get_client
            await client.flushdb()
            await client.aclose()

    asyncio.run(exercise())


def test_redis_quota_resets_in_a_new_window():
    async def exercise() -> None:
        client = Redis.from_url(REDIS_TEST_URL, decode_responses=False)
        original_get_client = rate_limit.get_redis_client
        rate_limit.get_redis_client = lambda: client
        try:
            await client.flushdb()
            limiter = RedisRateLimiter(limit=1, window=1, key_secret=b"z" * 48)
            assert (await limiter.check("2001:db8::9")).allowed is True
            assert (await limiter.check("2001:db8::9")).allowed is False
            await asyncio.sleep(1.1)
            assert (await limiter.check("2001:db8::9")).allowed is True
        finally:
            rate_limit.get_redis_client = original_get_client
            await client.flushdb()
            await client.aclose()

    asyncio.run(exercise())
