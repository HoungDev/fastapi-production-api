import os
import time
from uuid import uuid4

import pytest
from redis import Redis

from app.core.config import settings
from app.services.oidc_cache import OIDCPublicDocumentCache
from app.services.oidc_provider import OIDCProviderClient

REDIS_TEST_URL = os.environ.get("REDIS_TEST_URL")
pytestmark = pytest.mark.skipif(
    not REDIS_TEST_URL,
    reason="REDIS_TEST_URL is required for Redis integration tests",
)


def _discovery(issuer: str) -> dict:
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "jwks_uri": f"{issuer}/jwks",
        "code_challenge_methods_supported": ["S256"],
    }


def test_clients_share_ttl_cache_and_scoped_invalidation(monkeypatch):
    issuer = f"https://cache-test-{uuid4().hex}.example"
    redis = Redis.from_url(REDIS_TEST_URL, decode_responses=False)
    monkeypatch.setattr(settings, "OIDC_CACHE_BACKEND", "redis")
    monkeypatch.setattr(settings, "OIDC_ISSUER", issuer)
    monkeypatch.setattr(settings, "OIDC_DISCOVERY_CACHE_TTL_SECONDS", 30)
    monkeypatch.setattr(settings, "OIDC_CACHE_REFRESH_WAIT_SECONDS", 0)

    first_cache = OIDCPublicDocumentCache(redis)
    second_cache = OIDCPublicDocumentCache(redis)

    owned_keys = [
        first_cache.key("discovery"),
        first_cache.key("jwks"),
        first_cache.lock_key("discovery"),
        first_cache.lock_key("jwks"),
    ]
    redis.delete(*owned_keys)

    try:
        first = OIDCProviderClient(cache=first_cache)
        second = OIDCProviderClient(cache=second_cache)
        calls = 0

        def fetch(*args, **kwargs):
            nonlocal calls
            calls += 1
            return _discovery(issuer)

        monkeypatch.setattr(first, "_request_json", fetch)
        monkeypatch.setattr(
            second,
            "_request_json",
            lambda *args, **kwargs: pytest.fail("shared cache should satisfy request"),
        )

        assert first.discover().issuer == issuer
        assert second.discover().issuer == issuer
        assert calls == 1

        key = first_cache.key("discovery")
        assert issuer not in key
        assert 0 < redis.ttl(key) <= 30

        assert first_cache.invalidate() == 1
        assert redis.get(key) is None

        monkeypatch.setattr(second, "_request_json", fetch)

        assert second.discover().issuer == issuer
        assert calls == 2
        assert redis.get(key) is not None
        assert 0 < redis.ttl(key) <= 30
    finally:
        redis.delete(*owned_keys)
        redis.close()


def test_redis_outage_falls_through_to_provider(monkeypatch):
    issuer = f"https://cache-outage-{uuid4().hex}.example"

    broken_redis = Redis.from_url(
        "redis://127.0.0.1:1/15",
        decode_responses=False,
        socket_connect_timeout=0.1,
        socket_timeout=0.1,
    )

    monkeypatch.setattr(settings, "OIDC_CACHE_BACKEND", "redis")
    monkeypatch.setattr(settings, "OIDC_ISSUER", issuer)
    monkeypatch.setattr(settings, "OIDC_CACHE_REFRESH_WAIT_SECONDS", 0)

    cache = OIDCPublicDocumentCache(broken_redis)
    client = OIDCProviderClient(cache=cache)
    calls = 0

    def fetch(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _discovery(issuer)

    monkeypatch.setattr(client, "_request_json", fetch)

    try:
        assert client.discover().issuer == issuer
        assert calls == 1
    finally:
        broken_redis.close()


def test_refresh_lock_expires_and_can_be_recovered(monkeypatch):
    issuer = f"https://cache-lock-{uuid4().hex}.example"
    redis = Redis.from_url(REDIS_TEST_URL, decode_responses=False)

    monkeypatch.setattr(settings, "OIDC_CACHE_BACKEND", "redis")
    monkeypatch.setattr(settings, "OIDC_ISSUER", issuer)
    monkeypatch.setattr(settings, "OIDC_CACHE_REFRESH_LOCK_SECONDS", 1)

    cache = OIDCPublicDocumentCache(redis)
    owned_keys = [
        cache.lock_key("jwks"),
        cache.key("jwks"),
    ]
    redis.delete(*owned_keys)

    try:
        first = cache.acquire_refresh_lock("jwks")
        assert first is not None
        assert cache.acquire_refresh_lock("jwks") is None
        assert 0 < redis.ttl(cache.lock_key("jwks")) <= 1

        time.sleep(1.1)

        recovered = cache.acquire_refresh_lock("jwks")
        assert recovered is not None
        cache.release_refresh_lock("jwks", recovered)
    finally:
        redis.delete(*owned_keys)
        redis.close()
