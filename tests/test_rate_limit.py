from app.middlewares.rate_limit import RateLimiter


def test_rate_limiter_blocks_excess_requests():
    limiter = RateLimiter(
        limit=2,
        window=60,
    )

    assert limiter.is_allowed("127.0.0.1") is True
    assert limiter.is_allowed("127.0.0.1") is True
    assert limiter.is_allowed("127.0.0.1") is False