from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "FastAPI Production API"

    ENVIRONMENT: str = "development"

    DEBUG: bool = False


    DATABASE_URL: str


    SECRET_KEY: str

    ALGORITHM: str = "HS256"


    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    REFRESH_TOKEN_EXPIRE_DAYS: int = 7


    JWT_AUDIENCE: str = "fastapi-client"

    JWT_ISSUER: str = "fastapi-production-api"


    CORS_ORIGINS: str = ""


    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()