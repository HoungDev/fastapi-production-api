from app.core.config import settings


def test_settings_loaded():
    assert settings.APP_NAME == "FastAPI Production API"


def test_jwt_settings_loaded():
    assert settings.SECRET_KEY
    assert settings.ALGORITHM == "HS256"
    assert settings.JWT_AUDIENCE == "fastapi-client"
    assert settings.JWT_ISSUER == "fastapi-production-api"