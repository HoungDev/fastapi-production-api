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

    REDIS_URL: SecretStr = SecretStr("")

    REDIS_CONNECT_TIMEOUT_SECONDS: float = Field(default=1.0, gt=0, le=30)

    REDIS_SOCKET_TIMEOUT_SECONDS: float = Field(default=1.0, gt=0, le=30)

    REDIS_MAX_CONNECTIONS: int = Field(default=20, gt=0, le=1000)

    RATE_LIMIT_BACKEND: Literal["memory", "redis"] = "memory"

    RATE_LIMIT_LIMIT: int = Field(default=100, gt=0, le=1_000_000)

    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, gt=0, le=86_400)

    RATE_LIMIT_FAILURE_MODE: Literal["closed", "open"] = "closed"

    RATE_LIMIT_KEY_SECRET: SecretStr = SecretStr("")

    EMAIL_DELIVERY_MODE: Literal["disabled", "smtp"] = "disabled"

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

    SMTP_HOST: str = ""

    SMTP_PORT: int = 587

    SMTP_USERNAME: str = ""

    SMTP_PASSWORD: SecretStr = SecretStr("")

    SMTP_FROM: str = ""

    SMTP_STARTTLS: bool = True

    SMTP_TIMEOUT_SECONDS: int = 10

    @model_validator(mode="after")
    def validate_production_settings(self) -> Self:
        if self.RATE_LIMIT_BACKEND == "redis":
            redis_url_value = self.REDIS_URL.get_secret_value()
            redis_url = urlsplit(redis_url_value)
            if redis_url.scheme not in {"redis", "rediss"} or not redis_url.hostname:
                raise ValueError(
                    "REDIS_URL must be a redis:// or rediss:// URL when the Redis "
                    "rate-limit backend is enabled"
                )

            rate_limit_secret = self.RATE_LIMIT_KEY_SECRET.get_secret_value()
            if len(rate_limit_secret.encode("utf-8")) < 32:
                raise ValueError(
                    "RATE_LIMIT_KEY_SECRET must contain at least 32 bytes when "
                    "the Redis rate-limit backend is enabled"
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

        if self.EMAIL_DELIVERY_MODE == "smtp" and not (
            self.SMTP_HOST and self.SMTP_FROM
        ):
            raise ValueError(
                "SMTP_HOST and SMTP_FROM are required when SMTP delivery is enabled"
            )

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

        if self.EMAIL_DELIVERY_MODE == "smtp" and not all(
            url.startswith("https://")
            for url in (self.EMAIL_VERIFICATION_URL, self.PASSWORD_RESET_URL)
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
