import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError, ResponseError, TimeoutError

from app.middlewares import rate_limit
from app.middlewares.rate_limit import RateLimitDecision, setup_rate_limit


def create_test_app() -> FastAPI:
    test_app = FastAPI()
    setup_rate_limit(test_app)

    @test_app.get("/protected")
    def protected():
        return {"status": "ok"}

    @test_app.get("/health/live")
    def live():
        return {"status": "ok"}

    return test_app


class BrokenLimiter:
    def __init__(self, error=None):
        self.error = error or ConnectionError("sensitive backend detail")

    async def check(self, _: str):
        raise self.error


class AllowedLimiter:
    async def check(self, _: str):
        return RateLimitDecision(allowed=True, retry_after=1)


class BlockedLimiter:
    async def check(self, _: str):
        return RateLimitDecision(allowed=False, retry_after=23)


def configure_redis_backend(monkeypatch, limiter, failure_mode="closed"):
    monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setattr(
        rate_limit.settings,
        "RATE_LIMIT_FAILURE_MODE",
        failure_mode,
    )
    monkeypatch.setattr(rate_limit, "_redis_rate_limiter", lambda: limiter)


@pytest.mark.parametrize(
    "error",
    (
        ConnectionError("connection failed"),
        TimeoutError("operation timed out"),
        ResponseError("script failed"),
        OSError("socket failed"),
    ),
)
def test_redis_failure_is_fail_closed_by_default(monkeypatch, caplog, error):
    configure_redis_backend(monkeypatch, BrokenLimiter(error))

    response = TestClient(create_test_app()).get("/protected")

    assert response.status_code == 503
    assert response.json() == {"detail": "Rate limit service unavailable"}
    assert response.headers["retry-after"] == "1"
    assert "sensitive backend detail" not in caplog.text


def test_explicit_fail_open_policy_continues_request(monkeypatch):
    configure_redis_backend(monkeypatch, BrokenLimiter(), failure_mode="open")

    response = TestClient(create_test_app()).get("/protected")

    assert response.status_code == 200


def test_backend_recovery_restores_enforcement(monkeypatch):
    limiter = BrokenLimiter()
    configure_redis_backend(monkeypatch, limiter)
    test_client = TestClient(create_test_app())

    assert test_client.get("/protected").status_code == 503
    monkeypatch.setattr(rate_limit, "_redis_rate_limiter", lambda: AllowedLimiter())
    assert test_client.get("/protected").status_code == 200


def test_blocked_response_preserves_body_and_sets_retry_after(monkeypatch):
    configure_redis_backend(monkeypatch, BlockedLimiter())

    response = TestClient(create_test_app()).get("/protected")

    assert response.status_code == 429
    assert response.json() == {"detail": "Too many requests"}
    assert response.headers["retry-after"] == "23"


def test_exempt_path_never_calls_backend(monkeypatch):
    configure_redis_backend(monkeypatch, BrokenLimiter())

    response = TestClient(create_test_app()).get("/health/live")

    assert response.status_code == 200
