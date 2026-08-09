from redis.asyncio import Redis

from app.core.config import settings

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    global _redis_client

    if _redis_client is None:
        _redis_client = Redis.from_url(
            settings.REDIS_URL.get_secret_value(),
            decode_responses=False,
            socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            health_check_interval=30,
        )

    return _redis_client


async def close_redis_client() -> None:
    global _redis_client

    client = _redis_client
    _redis_client = None
    if client is not None:
        await client.aclose()
