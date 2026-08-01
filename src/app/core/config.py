from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "FastAPI Production API"
    DATABASE_URL: str = "sqlite:///app.db"


settings = Settings()