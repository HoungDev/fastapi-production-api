import json
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from redis.exceptions import ConnectionError

from app.core.config import settings
from app.services.oidc_cache import CACHE_NAMESPACE, OIDCPublicDocumentCache
from app.services.oidc_provider import (
    OIDCMetadata,
    OIDCProviderClient,
    OIDCProviderError,
)


class MemoryRedis:
    def __init__(self):
        self.values: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, *, ex=None, nx=False):
        if nx and key in self.values:
            return None
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def delete(self, *keys):
        deleted = 0
        for key in keys:
            deleted += key in self.values
            self.values.pop(key, None)
            self.ttls.pop(key, None)
        return deleted

    def eval(self, script, number_of_keys, key, token):
        if self.values.get(key) == token:
            return self.delete(key)
        return 0


class BrokenRedis:
    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise ConnectionError("redis://user:secret@cache.internal/0")

        return fail


@pytest.fixture
def cache_settings(monkeypatch):
    monkeypatch.setattr(settings, "OIDC_CACHE_BACKEND", "redis")
    monkeypatch.setattr(settings, "OIDC_ISSUER", "https://provider.example")
    monkeypatch.setattr(settings, "OIDC_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "OIDC_ALLOWED_ALGORITHMS", "RS256")
    monkeypatch.setattr(settings, "OIDC_DISCOVERY_CACHE_TTL_SECONDS", 60)
    monkeypatch.setattr(settings, "OIDC_JWKS_CACHE_TTL_SECONDS", 90)
    monkeypatch.setattr(settings, "OIDC_CACHE_REFRESH_LOCK_SECONDS", 5)
    monkeypatch.setattr(settings, "OIDC_CACHE_REFRESH_WAIT_SECONDS", 0)
    monkeypatch.setattr(settings, "OIDC_CACHE_MAX_DOCUMENT_BYTES", 262144)


def discovery_payload():
    issuer = settings.OIDC_ISSUER.rstrip("/")
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "jwks_uri": f"{issuer}/jwks",
        "code_challenge_methods_supported": ["S256"],
    }


def public_jwk(private_key, key_id):
    value = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    value.update({"kid": key_id, "alg": "RS256", "use": "sig"})
    return value


def signed_token(private_key, key_id):
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": settings.OIDC_ISSUER,
            "sub": "subject",
            "aud": settings.OIDC_CLIENT_ID,
            "nonce": "nonce",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": key_id},
    )


def test_validated_discovery_is_shared_without_raw_issuer(cache_settings, monkeypatch):
    redis = MemoryRedis()
    first = OIDCProviderClient(cache=OIDCPublicDocumentCache(redis))
    second = OIDCProviderClient(cache=OIDCPublicDocumentCache(redis))
    calls = 0

    def fetch(method, url, **kwargs):
        nonlocal calls
        calls += 1
        return discovery_payload()

    monkeypatch.setattr(first, "_request_json", fetch)
    monkeypatch.setattr(
        second,
        "_request_json",
        lambda *args, **kwargs: pytest.fail("provider should not be called"),
    )

    assert first.discover().issuer == settings.OIDC_ISSUER
    assert second.discover().issuer == settings.OIDC_ISSUER
    assert calls == 1
    key = first.cache.key("discovery")
    assert key.startswith(f"{CACHE_NAMESPACE}:")
    assert settings.OIDC_ISSUER not in key
    assert len(first.cache.issuer_digest) == 64
    assert redis.ttls[key] == 60


def test_poisoned_cache_is_deleted_and_refreshed(cache_settings, monkeypatch):
    redis = MemoryRedis()
    cache = OIDCPublicDocumentCache(redis)
    redis.set(
        cache.key("discovery"),
        json.dumps(
            {**discovery_payload(), "issuer": "https://attacker.example"}
        ).encode(),
        ex=60,
    )
    client = OIDCProviderClient(cache=cache)
    monkeypatch.setattr(
        client, "_request_json", lambda *args, **kwargs: discovery_payload()
    )

    assert client.discover().issuer == settings.OIDC_ISSUER
    assert (
        json.loads(redis.values[cache.key("discovery")])["issuer"]
        == settings.OIDC_ISSUER
    )


def test_redis_outage_falls_through_without_logging_secret(
    cache_settings, monkeypatch, caplog
):
    client = OIDCProviderClient(cache=OIDCPublicDocumentCache(BrokenRedis()))
    monkeypatch.setattr(
        client, "_request_json", lambda *args, **kwargs: discovery_payload()
    )

    assert client.discover().issuer == settings.OIDC_ISSUER
    assert "redis://user:secret" not in caplog.text


def test_unknown_cached_key_forces_one_refresh_and_accepts_rotation(
    cache_settings, monkeypatch
):
    old_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    redis = MemoryRedis()
    cache = OIDCPublicDocumentCache(redis)
    cache.write("jwks", {"keys": [public_jwk(old_key, "old-key")]})
    client = OIDCProviderClient(cache=cache)
    calls = 0

    def refresh(*args, **kwargs):
        nonlocal calls
        calls += 1
        return {"keys": [public_jwk(new_key, "new-key")]}

    monkeypatch.setattr(client, "_request_json", refresh)
    metadata = OIDCMetadata(
        issuer=settings.OIDC_ISSUER,
        authorization_endpoint=f"{settings.OIDC_ISSUER}/authorize",
        token_endpoint=f"{settings.OIDC_ISSUER}/token",
        jwks_uri=f"{settings.OIDC_ISSUER}/jwks",
    )

    claims = client.validate_id_token(metadata, signed_token(new_key, "new-key"))

    assert claims["sub"] == "subject"
    assert calls == 1


def test_unknown_key_after_forced_refresh_remains_rejected(cache_settings, monkeypatch):
    cached_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    unknown_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    redis = MemoryRedis()
    cache = OIDCPublicDocumentCache(redis)
    old_jwks = {"keys": [public_jwk(cached_key, "cached-key")]}
    cache.write("jwks", old_jwks)
    client = OIDCProviderClient(cache=cache)
    calls = 0

    def refresh(*args, **kwargs):
        nonlocal calls
        calls += 1
        return old_jwks

    monkeypatch.setattr(client, "_request_json", refresh)
    metadata = OIDCMetadata(
        issuer=settings.OIDC_ISSUER,
        authorization_endpoint=f"{settings.OIDC_ISSUER}/authorize",
        token_endpoint=f"{settings.OIDC_ISSUER}/token",
        jwks_uri=f"{settings.OIDC_ISSUER}/jwks",
    )

    with pytest.raises(OIDCProviderError, match="signing key was not found"):
        client.validate_id_token(metadata, signed_token(unknown_key, "unknown-key"))

    assert calls == 1


def test_oversized_provider_document_is_rejected(cache_settings, monkeypatch):
    monkeypatch.setattr(settings, "OIDC_CACHE_MAX_DOCUMENT_BYTES", 1024)
    client = OIDCProviderClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"{" + b"x" * 2048 + b"}")
        ),
        cache=OIDCPublicDocumentCache(MemoryRedis()),
    )

    with pytest.raises(OIDCProviderError, match="too large"):
        client.discover()
