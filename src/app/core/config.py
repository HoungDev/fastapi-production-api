from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "FastAPI Production API"
    DATABASE_URL: str = "sqlite:///app.db"

    SECRET_KEY: str = "your-secret-key"
    ALGORITHM: str = "HS256"


settings = Settings()