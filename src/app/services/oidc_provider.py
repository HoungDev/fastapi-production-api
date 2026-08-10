import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar
from urllib.parse import urlsplit

import httpx
import jwt

from app.core.config import settings
from app.core.metrics import (
    OIDC_PROVIDER_FETCH_DURATION_SECONDS,
    OIDC_PROVIDER_FETCHES_TOTAL,
)
from app.services.oidc_cache import CacheDocument, OIDCPublicDocumentCache

logger = logging.getLogger("fastapi-production-api.oidc_provider")
ValidatedDocument = TypeVar("ValidatedDocument")


class OIDCProviderError(Exception):
    pass


@dataclass(frozen=True)
class OIDCMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str


class OIDCProviderClient:
    def __init__(
        self,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
        cache: OIDCPublicDocumentCache | None = None,
    ):
        self.timeout = timeout or settings.OIDC_HTTP_TIMEOUT_SECONDS
        self.transport = transport
        self.cache = cache or OIDCPublicDocumentCache()

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        max_bytes: int | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                response = client.request(method, url, **kwargs)
                response.raise_for_status()
                if max_bytes is not None and len(response.content) > max_bytes:
                    raise OIDCProviderError("OIDC provider document is too large")
                payload = response.json()
        except OIDCProviderError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise OIDCProviderError("OIDC provider request failed") from exc
        if not isinstance(payload, dict):
            raise OIDCProviderError("OIDC provider returned an invalid response")
        return payload

    def _validate_discovery(self, payload: dict[str, Any]) -> OIDCMetadata:
        issuer = settings.OIDC_ISSUER.rstrip("/")
        try:
            metadata = OIDCMetadata(
                issuer=payload["issuer"],
                authorization_endpoint=payload["authorization_endpoint"],
                token_endpoint=payload["token_endpoint"],
                jwks_uri=payload["jwks_uri"],
            )
        except (KeyError, TypeError) as exc:
            raise OIDCProviderError("OIDC discovery metadata is incomplete") from exc

        if metadata.issuer != issuer:
            raise OIDCProviderError("OIDC discovery issuer mismatch")
        endpoints = (
            metadata.authorization_endpoint,
            metadata.token_endpoint,
            metadata.jwks_uri,
        )
        if not all(
            urlsplit(endpoint).scheme == "https"
            and bool(urlsplit(endpoint).netloc)
            and not urlsplit(endpoint).fragment
            and urlsplit(endpoint).username is None
            and urlsplit(endpoint).password is None
            for endpoint in endpoints
        ):
            raise OIDCProviderError("OIDC provider endpoints must use HTTPS")
        if "S256" not in payload.get("code_challenge_methods_supported", []):
            raise OIDCProviderError("OIDC provider does not advertise PKCE S256")
        return metadata

    @staticmethod
    def _validate_jwks(payload: dict[str, Any]) -> dict[str, Any]:
        keys = payload.get("keys")
        if (
            not isinstance(keys, list)
            or not keys
            or not all(isinstance(key, dict) for key in keys)
        ):
            raise OIDCProviderError("OIDC JWKS document is invalid")
        try:
            jwt.PyJWKSet.from_dict(payload)
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            raise OIDCProviderError("OIDC JWKS document is invalid") from exc
        return payload

    def _fetch_public_document(
        self,
        document: CacheDocument,
        url: str,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        try:
            payload = self._request_json(
                "GET",
                url,
                max_bytes=settings.OIDC_CACHE_MAX_DOCUMENT_BYTES,
            )
        except OIDCProviderError:
            OIDC_PROVIDER_FETCHES_TOTAL.labels(
                document=document,
                outcome="error",
            ).inc()
            raise
        else:
            OIDC_PROVIDER_FETCHES_TOTAL.labels(
                document=document,
                outcome="success",
            ).inc()
            return payload
        finally:
            OIDC_PROVIDER_FETCH_DURATION_SECONDS.labels(document=document).observe(
                time.perf_counter() - started_at
            )

    def _load_public_document(
        self,
        document: CacheDocument,
        url: str,
        validator: Callable[[dict[str, Any]], ValidatedDocument],
        *,
        force_refresh: bool = False,
        previous_payload: dict[str, Any] | None = None,
    ) -> tuple[ValidatedDocument, bool]:
        if not force_refresh:
            cached = self.cache.read(document)
            if cached.payload is not None:
                try:
                    validated = validator(cached.payload)
                except OIDCProviderError:
                    self.cache.reject(document)
                else:
                    self.cache.record_hit(document)
                    return validated, True

        lock = self.cache.acquire_refresh_lock(document)
        if lock is None and self.cache.enabled:
            waited = self.cache.wait_for_value(
                document,
                different_from=previous_payload if force_refresh else None,
            )
            if waited.payload is not None:
                try:
                    validated = validator(waited.payload)
                except OIDCProviderError:
                    self.cache.reject(document)
                else:
                    self.cache.record_hit(document)
                    return validated, True

        try:
            payload = self._fetch_public_document(document, url)
            validated = validator(payload)
            self.cache.write(document, payload)
            return validated, False
        finally:
            if lock is not None:
                self.cache.release_refresh_lock(document, lock)

    def discover(self) -> OIDCMetadata:
        issuer = settings.OIDC_ISSUER.rstrip("/")
        metadata, _ = self._load_public_document(
            "discovery",
            f"{issuer}/.well-known/openid-configuration",
            self._validate_discovery,
        )
        return metadata

    def exchange_code(
        self,
        metadata: OIDCMetadata,
        *,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> str:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": settings.OIDC_CLIENT_ID,
            "code_verifier": code_verifier,
        }
        kwargs: dict[str, Any] = {"data": data}
        secret = settings.OIDC_CLIENT_SECRET.get_secret_value()
        if settings.OIDC_TOKEN_ENDPOINT_AUTH_METHOD == "client_secret_basic":
            kwargs["auth"] = (settings.OIDC_CLIENT_ID, secret)
        else:
            data["client_secret"] = secret
        payload = self._request_json("POST", metadata.token_endpoint, **kwargs)
        id_token = payload.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise OIDCProviderError("OIDC token response did not contain an ID token")
        return id_token

    def validate_id_token(
        self,
        metadata: OIDCMetadata,
        id_token: str,
    ) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(id_token)
            algorithm = header.get("alg")
            key_id = header.get("kid")
            allowed = [
                value.strip()
                for value in settings.OIDC_ALLOWED_ALGORITHMS.split(",")
                if value.strip()
            ]
            if algorithm not in allowed or not key_id:
                raise OIDCProviderError("OIDC ID token header is not allowed")

            jwks, from_cache = self._load_public_document(
                "jwks",
                metadata.jwks_uri,
                self._validate_jwks,
            )
            keys = jwt.PyJWKSet.from_dict(jwks).keys
            signing_key = next(
                (
                    key
                    for key in keys
                    if key.key_id == key_id and key.algorithm_name == algorithm
                ),
                None,
            )
            if signing_key is None and from_cache:
                logger.info(
                    "oidc_jwks_forced_refresh",
                    extra={
                        "oidc_cache_event": "unknown_key_refresh",
                        "oidc_cache_document": "jwks",
                    },
                )
                jwks, _ = self._load_public_document(
                    "jwks",
                    metadata.jwks_uri,
                    self._validate_jwks,
                    force_refresh=True,
                    previous_payload=jwks,
                )
                keys = jwt.PyJWKSet.from_dict(jwks).keys
                signing_key = next(
                    (
                        key
                        for key in keys
                        if key.key_id == key_id and key.algorithm_name == algorithm
                    ),
                    None,
                )
            if signing_key is None:
                raise OIDCProviderError("OIDC signing key was not found")

            claims = jwt.decode(
                id_token,
                key=signing_key.key,
                algorithms=allowed,
                audience=settings.OIDC_CLIENT_ID,
                issuer=metadata.issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]},
            )
        except OIDCProviderError:
            raise
        except (jwt.PyJWTError, ValueError, TypeError, StopIteration) as exc:
            raise OIDCProviderError("OIDC ID token validation failed") from exc

        audience = claims.get("aud")
        if isinstance(audience, list) and len(audience) > 1:
            if claims.get("azp") != settings.OIDC_CLIENT_ID:
                raise OIDCProviderError("OIDC authorized party mismatch")
        elif claims.get("azp") not in (None, settings.OIDC_CLIENT_ID):
            raise OIDCProviderError("OIDC authorized party mismatch")
        return claims


def get_oidc_provider_client() -> OIDCProviderClient:
    return OIDCProviderClient()
