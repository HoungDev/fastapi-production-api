import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Literal

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.metrics import OIDC_CACHE_OPERATIONS_TOTAL
from app.core.redis import get_sync_redis_client

logger = logging.getLogger("fastapi-production-api.oidc_cache")

CacheDocument = Literal["discovery", "jwks"]
CACHE_NAMESPACE = "fastapi-production-api:oidc-cache:v1"
_RELEASE_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


@dataclass(frozen=True)
class CacheRead:
    payload: dict | None
    outcome: Literal["hit", "miss", "invalid", "error", "disabled"]


@dataclass(frozen=True)
class RefreshLock:
    key: str
    token: bytes


class OIDCPublicDocumentCache:
    def __init__(self, redis: Redis | None = None):
        self.enabled = settings.OIDC_CACHE_BACKEND == "redis"
        self.redis = redis
        if self.enabled and self.redis is None:
            self.redis = get_sync_redis_client()
        issuer = settings.OIDC_ISSUER.rstrip("/")
        self.issuer_digest = hashlib.sha256(issuer.encode("utf-8")).hexdigest()

    def key(self, document: CacheDocument) -> str:
        return f"{CACHE_NAMESPACE}:{self.issuer_digest}:{document}"

    def lock_key(self, document: CacheDocument) -> str:
        return f"{self.key(document)}:refresh-lock"

    def read(self, document: CacheDocument) -> CacheRead:
        if not self.enabled or self.redis is None:
            return CacheRead(None, "disabled")
        try:
            value = self.redis.get(self.key(document))
        except (RedisError, OSError, TimeoutError):
            self._record(document, "error")
            self._warning("read_error", document)
            return CacheRead(None, "error")
        if value is None:
            self._record(document, "miss")
            return CacheRead(None, "miss")
        if len(value) > settings.OIDC_CACHE_MAX_DOCUMENT_BYTES:
            self._discard_invalid(document)
            return CacheRead(None, "invalid")
        try:
            payload = json.loads(value)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._discard_invalid(document)
            return CacheRead(None, "invalid")
        if not isinstance(payload, dict):
            self._discard_invalid(document)
            return CacheRead(None, "invalid")
        return CacheRead(payload, "hit")

    def record_hit(self, document: CacheDocument) -> None:
        self._record(document, "hit")

    def reject(self, document: CacheDocument) -> None:
        self._discard_invalid(document)

    def write(self, document: CacheDocument, payload: dict) -> bool:
        if not self.enabled or self.redis is None:
            return False
        value = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(value) > settings.OIDC_CACHE_MAX_DOCUMENT_BYTES:
            self._record(document, "invalid")
            return False
        ttl = (
            settings.OIDC_DISCOVERY_CACHE_TTL_SECONDS
            if document == "discovery"
            else settings.OIDC_JWKS_CACHE_TTL_SECONDS
        )
        try:
            self.redis.set(self.key(document), value, ex=ttl)
        except (RedisError, OSError, TimeoutError):
            self._record(document, "error")
            self._warning("write_error", document)
            return False
        self._record(document, "refreshed")
        return True

    def acquire_refresh_lock(self, document: CacheDocument) -> RefreshLock | None:
        if not self.enabled or self.redis is None:
            return None
        token = secrets.token_bytes(16)
        try:
            acquired = self.redis.set(
                self.lock_key(document),
                token,
                nx=True,
                ex=settings.OIDC_CACHE_REFRESH_LOCK_SECONDS,
            )
        except (RedisError, OSError, TimeoutError):
            self._record(document, "lock_error")
            self._warning("lock_error", document)
            return None
        if acquired:
            self._record(document, "lock_acquired")
            return RefreshLock(self.lock_key(document), token)
        self._record(document, "lock_contended")
        return None

    def release_refresh_lock(self, document: CacheDocument, lock: RefreshLock) -> None:
        if self.redis is None:
            return
        try:
            self.redis.eval(_RELEASE_LOCK_SCRIPT, 1, lock.key, lock.token)
        except (RedisError, OSError, TimeoutError):
            self._record(document, "lock_error")
            self._warning("lock_release_error", document)

    def wait_for_value(
        self,
        document: CacheDocument,
        *,
        different_from: dict | None = None,
    ) -> CacheRead:
        deadline = time.monotonic() + settings.OIDC_CACHE_REFRESH_WAIT_SECONDS
        while time.monotonic() < deadline:
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
            result = self.read(document)
            if (
                result.payload is not None
                and result.payload != different_from
                or result.outcome in {"error", "invalid", "disabled"}
            ):
                return result
        return CacheRead(None, "miss")

    def invalidate(self) -> int | None:
        if not self.enabled or self.redis is None:
            return None
        keys = [self.key("discovery"), self.key("jwks")]
        try:
            deleted = int(self.redis.delete(*keys))
        except (RedisError, OSError, TimeoutError):
            self._record("discovery", "invalidation_error")
            self._record("jwks", "invalidation_error")
            self._warning("invalidation_error", "discovery")
            return None
        self._record("discovery", "invalidated")
        self._record("jwks", "invalidated")
        return deleted

    def _discard_invalid(self, document: CacheDocument) -> None:
        self._record(document, "invalid")
        if self.redis is not None:
            try:
                self.redis.delete(self.key(document))
            except (RedisError, OSError, TimeoutError):
                self._warning("invalid_entry_delete_error", document)

    @staticmethod
    def _record(document: CacheDocument, outcome: str) -> None:
        OIDC_CACHE_OPERATIONS_TOTAL.labels(document=document, outcome=outcome).inc()

    @staticmethod
    def _warning(event: str, document: CacheDocument) -> None:
        logger.warning(
            "oidc_cache_event",
            extra={"oidc_cache_event": event, "oidc_cache_document": document},
        )
