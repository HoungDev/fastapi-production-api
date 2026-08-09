import pytest

from app.core.config import Settings, settings


def test_settings_loaded():
    assert settings.APP_NAME == "FastAPI Production API"


def test_jwt_settings_loaded():
    assert settings.SECRET_KEY
    assert settings.ALGORITHM == "HS256"
    assert settings.JWT_AUDIENCE == "fastapi-client"
    assert settings.JWT_ISSUER == "fastapi-production-api"


def test_production_rejects_short_secret():
    with pytest.raises(ValueError, match="at least 32 bytes"):
        Settings(
            DATABASE_URL="sqlite:///test.db",
            SECRET_KEY="too-short",
            ENVIRONMENT="production",
            _env_file=None,
        )


def test_production_rejects_debug_mode():
    with pytest.raises(ValueError, match="DEBUG must be false"):
        Settings(
            DATABASE_URL="sqlite:///test.db",
            SECRET_KEY="a" * 48,
            ENVIRONMENT="production",
            DEBUG=True,
            _env_file=None,
        )


def test_smtp_delivery_requires_host_and_sender():
    with pytest.raises(ValueError, match="SMTP_HOST and SMTP_FROM"):
        Settings(
            DATABASE_URL="sqlite:///test.db",
            SECRET_KEY="local-test-secret",
            EMAIL_DELIVERY_MODE="smtp",
            _env_file=None,
        )


def test_production_smtp_requires_https_action_urls():
    with pytest.raises(ValueError, match="must use HTTPS"):
        Settings(
            DATABASE_URL="sqlite:///test.db",
            SECRET_KEY="a" * 48,
            ENVIRONMENT="production",
            EMAIL_DELIVERY_MODE="smtp",
            SMTP_HOST="smtp.example.com",
            SMTP_FROM="security@example.com",
            EMAIL_VERIFICATION_URL="https://app.example.com/verify-email",
            PASSWORD_RESET_URL="http://app.example.com/reset-password",
            _env_file=None,
        )
