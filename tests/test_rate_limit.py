from app.middlewares import rate_limit
from app.middlewares.rate_limit import RateLimiter


def test_rate_limiter_blocks_excess_requests():
    limiter = RateLimiter(
        limit=2,
        window=60,
    )

    assert limiter.is_allowed("127.0.0.1") is True
    assert limiter.is_allowed("127.0.0.1") is True
    assert limiter.is_allowed("127.0.0.1") is False


def test_rate_limiter_tracks_clients_independently():
    limiter = RateLimiter(limit=1, window=60)

    assert limiter.is_allowed("192.0.2.1") is True
    assert limiter.is_allowed("192.0.2.1") is False
    assert limiter.is_allowed("192.0.2.2") is True


def test_rate_limiter_allows_requests_after_window_expires(monkeypatch):
    current_time = 1000.0
    monkeypatch.setattr(rate_limit.time, "time", lambda: current_time)
    limiter = RateLimiter(limit=1, window=60)

    assert limiter.is_allowed("192.0.2.1") is True
    assert limiter.is_allowed("192.0.2.1") is False

    current_time += 61

    assert limiter.is_allowed("192.0.2.1") is True
