import hashlib
import hmac
import ipaddress
import logging
import math
import time
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

from app.core.client_ip import resolve_client_ip
from app.core.config import settings
from app.core.metrics import (
    RATE_LIMIT_BACKEND_ERRORS_TOTAL,
    RATE_LIMIT_DECISIONS_TOTAL,
)
from app.core.redis import get_redis_client

RATE_LIMIT_EXEMPT_PATHS = frozenset(
    {
        "/health",
        "/health/db",
        "/health/live",
        "/health/ready",
        "/metrics",
    }
)
REDIS_RATE_LIMIT_SCRIPT = """
local now = redis.call('TIME')
local seconds = tonumber(now[1])
local window = tonumber(ARGV[1])
local bucket = math.floor(seconds / window)
local key = ARGV[2] .. bucket
local count = redis.call('INCR', key)
local maximum_ttl = window * 2
if count == 1 or redis.call('TTL', key) < 0 then
    redis.call('EXPIRE', key, maximum_ttl)
end
local retry_after = window - (seconds % window)
return {count, retry_after}
"""

logger = logging.getLogger("fastapi-production-api.rate_limit")


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int


class RateLimiter:
    def __init__(self, limit: int = 100, window: int = 60):
        self.limit = limit
        self.window = window
        self.requests: dict[str, tuple[int, int]] = {}

    def cleanup(self) -> None:
        current_window = math.floor(time.time() / self.window)
        self.requests = {
            client: state
            for client, state in self.requests.items()
            if state[0] >= current_window
        }

    def check(self, client: str) -> RateLimitDecision:
        current_time = time.time()
        current_window = math.floor(current_time / self.window)
        self.cleanup()
        stored_window, count = self.requests.get(client, (current_window, 0))
        if stored_window != current_window:
            count = 0
        count += 1
        self.requests[client] = (current_window, count)
        retry_after = max(1, self.window - math.floor(current_time % self.window))
        return RateLimitDecision(count <= self.limit, retry_after)

    def is_allowed(self, client_ip: str) -> bool:
        return self.check(client_ip).allowed


class RedisRateLimiter:
    def __init__(self, *, limit: int, window: int, key_secret: bytes):
        self.limit = limit
        self.window = window
        self.key_secret = key_secret

    @staticmethod
    def normalize_client(value: str) -> str:
        candidate = value.strip()
        try:
            return ipaddress.ip_address(candidate).compressed
        except ValueError:
            return candidate.casefold()[:255] or "unknown"

    def key_prefix(self, client: str) -> str:
        normalized = self.normalize_client(client)
        identifier = hmac.new(
            self.key_secret,
            b"fastapi-production-api:rate-limit:v1:" + normalized.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"fpapi:rate-limit:v1:{identifier}:"

    async def check(self, client: str) -> RateLimitDecision:
        result = await get_redis_client().eval(
            REDIS_RATE_LIMIT_SCRIPT,
            0,
            self.window,
            self.key_prefix(client),
        )
        count, retry_after = (int(value) for value in result)
        return RateLimitDecision(count <= self.limit, max(1, retry_after))


rate_limiter = RateLimiter(
    limit=settings.RATE_LIMIT_LIMIT,
    window=settings.RATE_LIMIT_WINDOW_SECONDS,
)


def _redis_rate_limiter() -> RedisRateLimiter:
    return RedisRateLimiter(
        limit=settings.RATE_LIMIT_LIMIT,
        window=settings.RATE_LIMIT_WINDOW_SECONDS,
        key_secret=settings.RATE_LIMIT_KEY_SECRET.get_secret_value().encode("utf-8"),
    )


def _client_address(request: Request) -> str:
    return resolve_client_ip(request)


def setup_rate_limit(app: FastAPI) -> None:
    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if request.url.path in RATE_LIMIT_EXEMPT_PATHS:
            return await call_next(request)

        backend = settings.RATE_LIMIT_BACKEND
        try:
            if backend == "redis":
                decision = await _redis_rate_limiter().check(_client_address(request))
            else:
                decision = rate_limiter.check(_client_address(request))
        except (RedisError, OSError, TimeoutError):
            RATE_LIMIT_BACKEND_ERRORS_TOTAL.labels(
                backend="redis", operation="decision"
            ).inc()
            if settings.RATE_LIMIT_FAILURE_MODE == "open":
                RATE_LIMIT_DECISIONS_TOTAL.labels(
                    backend="redis", outcome="fail_open"
                ).inc()
                logger.warning(
                    "rate_limit_backend_unavailable",
                    extra={
                        "rate_limit_backend": "redis",
                        "rate_limit_policy": "open",
                        "rate_limit_operation": "decision",
                    },
                )
                return await call_next(request)

            RATE_LIMIT_DECISIONS_TOTAL.labels(
                backend="redis", outcome="fail_closed"
            ).inc()
            logger.warning(
                "rate_limit_backend_unavailable",
                extra={
                    "rate_limit_backend": "redis",
                    "rate_limit_policy": "closed",
                    "rate_limit_operation": "decision",
                },
            )
            return JSONResponse(
                status_code=503,
                content={"detail": "Rate limit service unavailable"},
                headers={"Retry-After": "1"},
            )

        outcome = "allowed" if decision.allowed else "blocked"
        RATE_LIMIT_DECISIONS_TOTAL.labels(backend=backend, outcome=outcome).inc()
        if not decision.allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests"},
                headers={"Retry-After": str(decision.retry_after)},
            )

        return await call_next(request)
