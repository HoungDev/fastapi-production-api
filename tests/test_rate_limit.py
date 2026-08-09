import asyncio

from fastapi import Request

from app.middlewares import rate_limit
from app.middlewares.rate_limit import RateLimiter, RedisRateLimiter


def test_rate_limiter_blocks_excess_requests():
    limiter = RateLimiter(limit=2, window=60)

    assert limiter.is_allowed("127.0.0.1") is True
    assert limiter.is_allowed("127.0.0.1") is True
    assert limiter.is_allowed("127.0.0.1") is False


def test_rate_limiter_tracks_clients_independently():
    limiter = RateLimiter(limit=1, window=60)

    assert limiter.is_allowed("192.0.2.1") is True
    assert limiter.is_allowed("192.0.2.1") is False
    assert limiter.is_allowed("192.0.2.2") is True


def test_rate_limiter_allows_requests_in_a_new_window(monkeypatch):
    current_time = 1020.0
    monkeypatch.setattr(rate_limit.time, "time", lambda: current_time)
    limiter = RateLimiter(limit=1, window=60)

    assert limiter.is_allowed("192.0.2.1") is True
    assert limiter.is_allowed("192.0.2.1") is False

    current_time += 60

    assert limiter.is_allowed("192.0.2.1") is True


def test_redis_key_is_versioned_bounded_and_privacy_preserving():
    limiter = RedisRateLimiter(limit=2, window=60, key_secret=b"k" * 48)

    key = limiter.key_prefix("2001:0db8:0000:0000:0000:0000:0000:0001")

    assert key.startswith("fpapi:rate-limit:v1:")
    assert len(key) == len("fpapi:rate-limit:v1::") + 64
    assert "2001" not in key
    assert "db8" not in key
    assert RedisRateLimiter.normalize_client("2001:0db8::1") == "2001:db8::1"


def test_forwarded_headers_do_not_change_the_asgi_client_address():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-forwarded-for", b"198.51.100.9")],
            "client": ("192.0.2.10", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )

    assert rate_limit._client_address(request) == "192.0.2.10"


def test_redis_limiter_uses_one_atomic_script(monkeypatch):
    calls = []

    class FakeRedis:
        async def eval(self, *args):
            calls.append(args)
            return [2, 17]

    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: FakeRedis())
    limiter = RedisRateLimiter(limit=2, window=60, key_secret=b"s" * 48)

    decision = asyncio.run(limiter.check("192.0.2.1"))

    assert decision.allowed is True
    assert decision.retry_after == 17
    assert len(calls) == 1
    assert calls[0][1:3] == (0, 60)
    assert "192.0.2.1" not in calls[0][3]
