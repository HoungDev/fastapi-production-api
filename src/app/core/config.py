from typing import Self

from pydantic import model_validator
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

    @model_validator(mode="after")
    def validate_production_settings(self) -> Self:
        if self.ENVIRONMENT.lower() != "production":
            return self

        placeholder_secrets = {
            "change_this_to_a_random_secret_key",
            "generate_a_secure_random_secret_key",
            "your-secret-key",
        }

        if self.DEBUG:
            raise ValueError("DEBUG must be false in production")

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
    )


settings = Settings()
