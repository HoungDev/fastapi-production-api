import ipaddress
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "FastAPI Production API"

    ENVIRONMENT: str = "development"

    DEBUG: bool = False

    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str

    SECRET_KEY: str

    ALGORITHM: str = "HS256"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    JWT_AUDIENCE: str = "fastapi-client"

    JWT_ISSUER: str = "fastapi-production-api"

    CORS_ORIGINS: str = ""

    FORWARDED_ALLOW_IPS: str = ""

    REDIS_URL: SecretStr = SecretStr("")

    REDIS_CONNECT_TIMEOUT_SECONDS: float = Field(default=1.0, gt=0, le=30)

    REDIS_SOCKET_TIMEOUT_SECONDS: float = Field(default=1.0, gt=0, le=30)

    REDIS_MAX_CONNECTIONS: int = Field(default=20, gt=0, le=1000)

    RATE_LIMIT_BACKEND: Literal["memory", "redis"] = "memory"

    RATE_LIMIT_LIMIT: int = Field(default=100, gt=0, le=1_000_000)

    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, gt=0, le=86_400)

    RATE_LIMIT_FAILURE_MODE: Literal["closed", "open"] = "closed"

    RATE_LIMIT_KEY_SECRET: SecretStr = SecretStr("")

    EMAIL_DELIVERY_MODE: Literal["disabled", "smtp", "outbox"] = "disabled"

    OUTBOX_ENCRYPTION_KEY: SecretStr = SecretStr("")

    OUTBOX_POLL_INTERVAL_SECONDS: float = Field(default=1.0, gt=0, le=60)

    OUTBOX_BATCH_SIZE: int = Field(default=10, gt=0, le=100)

    OUTBOX_LEASE_SECONDS: int = Field(default=30, gt=0, le=3600)

    OUTBOX_MAX_ATTEMPTS: int = Field(default=5, gt=0, le=100)

    OUTBOX_BACKOFF_BASE_SECONDS: int = Field(default=5, gt=0, le=3600)

    OUTBOX_BACKOFF_MAX_SECONDS: int = Field(default=300, gt=0, le=86400)

    OUTBOX_SHUTDOWN_GRACE_SECONDS: int = Field(default=30, gt=0, le=3600)

    EMAIL_VERIFICATION_URL: str = "http://localhost:3000/verify-email"

    EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES: int = 30

    PASSWORD_RESET_URL: str = "http://localhost:3000/reset-password"

    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30

    MFA_ENABLED: bool = False

    MFA_ISSUER: str = "FastAPI Production API"

    MFA_ENCRYPTION_KEY: SecretStr = SecretStr("")

    MFA_ENROLLMENT_EXPIRE_MINUTES: int = 10

    MFA_CHALLENGE_EXPIRE_MINUTES: int = 5

    MFA_RECOVERY_CODE_COUNT: int = 10

    MFA_STEP_UP_MAX_AGE_MINUTES: int = 10

    OIDC_ENABLED: bool = False

    OIDC_ISSUER: str = ""

    OIDC_CLIENT_ID: str = ""

    OIDC_CLIENT_SECRET: SecretStr = SecretStr("")

    OIDC_REDIRECT_URI: str = "http://localhost:8000/auth/oidc/callback"

    OIDC_SCOPES: str = "openid email profile"

    OIDC_ALLOWED_ALGORITHMS: str = "RS256"

    OIDC_TOKEN_ENDPOINT_AUTH_METHOD: Literal[
        "client_secret_basic", "client_secret_post"
    ] = "client_secret_basic"

    OIDC_TRANSACTION_ENCRYPTION_KEY: SecretStr = SecretStr("")

    OIDC_TRANSACTION_EXPIRE_MINUTES: int = 5

    OIDC_RECENT_AUTH_MAX_AGE_MINUTES: int = 10

    OIDC_HTTP_TIMEOUT_SECONDS: float = 5.0

    OIDC_CACHE_BACKEND: Literal["none", "redis"] = "none"

    OIDC_DISCOVERY_CACHE_TTL_SECONDS: int = Field(default=300, gt=0, le=86400)

    OIDC_JWKS_CACHE_TTL_SECONDS: int = Field(default=300, gt=0, le=86400)

    OIDC_CACHE_REFRESH_LOCK_SECONDS: int = Field(default=5, gt=0, le=60)

    OIDC_CACHE_REFRESH_WAIT_SECONDS: float = Field(default=1.0, ge=0, le=10)

    OIDC_CACHE_MAX_DOCUMENT_BYTES: int = Field(
        default=262144,
        ge=1024,
        le=1048576,
    )

    TRACING_ENABLED: bool = False

    OTEL_SERVICE_NAME: str = "fastapi-production-api"

    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4318"

    OTEL_EXPORT_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0, le=30)

    OTEL_TRACE_SAMPLE_RATIO: float = Field(default=1.0, ge=0.0, le=1.0)

    SMTP_HOST: str = ""

    SMTP_PORT: int = 587

    SMTP_USERNAME: str = ""

    SMTP_PASSWORD: SecretStr = SecretStr("")

    SMTP_FROM: str = ""

    SMTP_STARTTLS: bool = True

    SMTP_TIMEOUT_SECONDS: int = 10

    @model_validator(mode="after")
    def validate_production_settings(self) -> Self:
        trusted_proxies = self.FORWARDED_ALLOW_IPS.split(",")
        if self.FORWARDED_ALLOW_IPS and any(
            not value.strip() for value in trusted_proxies
        ):
            raise ValueError("FORWARDED_ALLOW_IPS must not contain empty entries")

        for trusted_proxy in trusted_proxies:
            trusted_proxy = trusted_proxy.strip()
            if not trusted_proxy:
                continue

            if trusted_proxy == "*":
                raise ValueError("FORWARDED_ALLOW_IPS must not trust every client")

            try:
                if "/" in trusted_proxy:
                    ipaddress.ip_network(trusted_proxy, strict=True)
                else:
                    ipaddress.ip_address(trusted_proxy)
            except ValueError as exc:
                raise ValueError(
                    "FORWARDED_ALLOW_IPS must contain only valid IP addresses "
                    "or canonical CIDR networks"
                ) from exc

        if self.RATE_LIMIT_BACKEND == "redis" or self.OIDC_CACHE_BACKEND == "redis":
            redis_url_value = self.REDIS_URL.get_secret_value()
            redis_url = urlsplit(redis_url_value)
            if redis_url.scheme not in {"redis", "rediss"} or not redis_url.hostname:
                raise ValueError(
                    "REDIS_URL must be a redis:// or rediss:// URL when a Redis "
                    "backend is enabled"
                )

        if self.RATE_LIMIT_BACKEND == "redis":
            rate_limit_secret = self.RATE_LIMIT_KEY_SECRET.get_secret_value()
            if len(rate_limit_secret.encode("utf-8")) < 32:
                raise ValueError(
                    "RATE_LIMIT_KEY_SECRET must contain at least 32 bytes when "
                    "the Redis rate-limit backend is enabled"
                )

        if (
            self.OIDC_CACHE_BACKEND == "redis"
            and self.OIDC_CACHE_REFRESH_WAIT_SECONDS
            >= self.OIDC_CACHE_REFRESH_LOCK_SECONDS
        ):
            raise ValueError(
                "OIDC_CACHE_REFRESH_WAIT_SECONDS must be less than "
                "OIDC_CACHE_REFRESH_LOCK_SECONDS"
            )

        if self.EMAIL_DELIVERY_MODE == "outbox":
            from cryptography.fernet import Fernet

            try:
                Fernet(self.OUTBOX_ENCRYPTION_KEY.get_secret_value().encode("ascii"))
            except (TypeError, ValueError, UnicodeError) as exc:
                raise ValueError(
                    "OUTBOX_ENCRYPTION_KEY must be a valid Fernet key when "
                    "transactional delivery is enabled"
                ) from exc

            if self.OUTBOX_BACKOFF_MAX_SECONDS < self.OUTBOX_BACKOFF_BASE_SECONDS:
                raise ValueError(
                    "OUTBOX_BACKOFF_MAX_SECONDS must be greater than or equal to "
                    "OUTBOX_BACKOFF_BASE_SECONDS"
                )

            if self.OUTBOX_LEASE_SECONDS <= self.SMTP_TIMEOUT_SECONDS:
                raise ValueError(
                    "OUTBOX_LEASE_SECONDS must be greater than SMTP_TIMEOUT_SECONDS"
                )

            if self.OUTBOX_SHUTDOWN_GRACE_SECONDS < self.SMTP_TIMEOUT_SECONDS:
                raise ValueError(
                    "OUTBOX_SHUTDOWN_GRACE_SECONDS must be at least "
                    "SMTP_TIMEOUT_SECONDS"
                )

        if self.MFA_ENABLED:
            from cryptography.fernet import Fernet

            try:
                Fernet(self.MFA_ENCRYPTION_KEY.get_secret_value().encode("ascii"))
            except (TypeError, ValueError, UnicodeError) as exc:
                raise ValueError(
                    "MFA_ENCRYPTION_KEY must be a valid Fernet key when MFA is enabled"
                ) from exc

        if self.OIDC_ENABLED:
            from cryptography.fernet import Fernet

            required = (
                self.OIDC_ISSUER,
                self.OIDC_CLIENT_ID,
                self.OIDC_CLIENT_SECRET.get_secret_value(),
            )

            if not all(required):
                raise ValueError(
                    "OIDC_ISSUER, OIDC_CLIENT_ID, and OIDC_CLIENT_SECRET are "
                    "required when OIDC is enabled"
                )

            if "openid" not in self.OIDC_SCOPES.split():
                raise ValueError("OIDC_SCOPES must include openid")

            if not self.OIDC_ALLOWED_ALGORITHMS.strip():
                raise ValueError("OIDC_ALLOWED_ALGORITHMS cannot be empty")

            allowed_algorithms = {
                value.strip()
                for value in self.OIDC_ALLOWED_ALGORITHMS.split(",")
                if value.strip()
            }

            asymmetric_algorithms = {
                "RS256",
                "RS384",
                "RS512",
                "PS256",
                "PS384",
                "PS512",
                "ES256",
                "ES384",
                "ES512",
                "EdDSA",
            }

            if not allowed_algorithms <= asymmetric_algorithms:
                raise ValueError(
                    "OIDC_ALLOWED_ALGORITHMS must contain only asymmetric signing "
                    "algorithms"
                )

            issuer = urlsplit(self.OIDC_ISSUER)
            redirect = urlsplit(self.OIDC_REDIRECT_URI)

            if (
                issuer.scheme != "https"
                or not issuer.netloc
                or issuer.query
                or issuer.fragment
            ):
                raise ValueError(
                    "OIDC_ISSUER must be an HTTPS URL without query or fragment"
                )

            if len(self.OIDC_ISSUER.rstrip("/")) > 255:
                raise ValueError("OIDC_ISSUER must not exceed 255 characters")

            if not redirect.scheme or not redirect.netloc or redirect.fragment:
                raise ValueError(
                    "OIDC_REDIRECT_URI must be an absolute URL without fragment"
                )

            try:
                Fernet(
                    self.OIDC_TRANSACTION_ENCRYPTION_KEY.get_secret_value().encode(
                        "ascii"
                    )
                )
            except (TypeError, ValueError, UnicodeError) as exc:
                raise ValueError(
                    "OIDC_TRANSACTION_ENCRYPTION_KEY must be a valid Fernet key "
                    "when OIDC is enabled"
                ) from exc

        if self.EMAIL_DELIVERY_MODE in {"smtp", "outbox"} and not (
            self.SMTP_HOST and self.SMTP_FROM
        ):
            raise ValueError(
                "SMTP_HOST and SMTP_FROM are required when SMTP delivery is enabled"
            )

        if self.TRACING_ENABLED:
            endpoint = urlsplit(self.OTEL_EXPORTER_OTLP_ENDPOINT)

            if endpoint.scheme not in {"http", "https"} or not endpoint.netloc:
                raise ValueError(
                    "OTEL_EXPORTER_OTLP_ENDPOINT must be an absolute http:// or "
                    "https:// URL when tracing is enabled"
                )

            if endpoint.username is not None or endpoint.password is not None:
                raise ValueError(
                    "OTEL_EXPORTER_OTLP_ENDPOINT must not contain embedded credentials"
                )

            if not self.OTEL_SERVICE_NAME.strip():
                raise ValueError(
                    "OTEL_SERVICE_NAME cannot be empty when tracing is enabled"
                )

            if len(self.OTEL_SERVICE_NAME) > 128:
                raise ValueError("OTEL_SERVICE_NAME must not exceed 128 characters")

        if self.ENVIRONMENT.lower() != "production":
            return self

        placeholder_secrets = {
            "change_this_to_a_random_secret_key",
            "generate_a_secure_random_secret_key",
            "your-secret-key",
        }

        if (
            self.RATE_LIMIT_BACKEND == "redis"
            and self.RATE_LIMIT_KEY_SECRET.get_secret_value()
            in {
                "change_this_to_a_random_rate_limit_key",
                "generate_a_secure_random_rate_limit_key",
            }
        ):
            raise ValueError(
                "RATE_LIMIT_KEY_SECRET must not use a placeholder in production"
            )

        if self.DEBUG:
            raise ValueError("DEBUG must be false in production")

        if self.EMAIL_DELIVERY_MODE in {"smtp", "outbox"} and not all(
            url.startswith("https://")
            for url in (
                self.EMAIL_VERIFICATION_URL,
                self.PASSWORD_RESET_URL,
            )
        ):
            raise ValueError("Email action URLs must use HTTPS in production")

        if self.OIDC_ENABLED and urlsplit(self.OIDC_REDIRECT_URI).scheme != "https":
            raise ValueError("OIDC_REDIRECT_URI must use HTTPS in production")

        if (
            len(self.SECRET_KEY.encode("utf-8")) < 32
            or self.SECRET_KEY in placeholder_secrets
        ):
            raise ValueError(
                "SECRET_KEY must contain at least 32 bytes of non-placeholder "
                "data in production"
            )

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        hide_input_in_errors=True,
    )


settings = Settings()
