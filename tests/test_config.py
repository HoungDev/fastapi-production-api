import pytest
from cryptography.fernet import Fernet

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


def test_mfa_requires_valid_encryption_key_when_enabled():
    with pytest.raises(ValueError, match="valid Fernet key"):
        Settings(
            DATABASE_URL="sqlite:///test.db",
            SECRET_KEY="local-test-secret",
            MFA_ENABLED=True,
            MFA_ENCRYPTION_KEY="not-a-fernet-key",
            _env_file=None,
        )


def test_mfa_accepts_dedicated_fernet_key():
    configured = Settings(
        DATABASE_URL="sqlite:///test.db",
        SECRET_KEY="local-test-secret",
        MFA_ENABLED=True,
        MFA_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
        _env_file=None,
    )

    assert configured.MFA_ENABLED is True


def test_oidc_requires_complete_secure_configuration():
    with pytest.raises(ValueError, match="OIDC_ISSUER"):
        Settings(
            DATABASE_URL="sqlite:///test.db",
            SECRET_KEY="local-test-secret",
            OIDC_ENABLED=True,
            _env_file=None,
        )


def test_oidc_requires_pkce_transaction_key():
    with pytest.raises(ValueError, match="valid Fernet key"):
        Settings(
            DATABASE_URL="sqlite:///test.db",
            SECRET_KEY="local-test-secret",
            OIDC_ENABLED=True,
            OIDC_ISSUER="https://issuer.example",
            OIDC_CLIENT_ID="client-id",
            OIDC_CLIENT_SECRET="client-secret",
            OIDC_TRANSACTION_ENCRYPTION_KEY="invalid",
            _env_file=None,
        )


def test_production_oidc_requires_https_redirect():
    with pytest.raises(ValueError, match="must use HTTPS in production"):
        Settings(
            DATABASE_URL="sqlite:///test.db",
            SECRET_KEY="a" * 48,
            ENVIRONMENT="production",
            OIDC_ENABLED=True,
            OIDC_ISSUER="https://issuer.example",
            OIDC_CLIENT_ID="client-id",
            OIDC_CLIENT_SECRET="client-secret",
            OIDC_REDIRECT_URI="http://localhost/auth/oidc/callback",
            OIDC_TRANSACTION_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
            _env_file=None,
        )


def test_oidc_rejects_symmetric_id_token_algorithms():
    with pytest.raises(ValueError, match="asymmetric signing algorithms"):
        Settings(
            DATABASE_URL="sqlite:///test.db",
            SECRET_KEY="local-test-secret",
            OIDC_ENABLED=True,
            OIDC_ISSUER="https://issuer.example",
            OIDC_CLIENT_ID="client-id",
            OIDC_CLIENT_SECRET="client-secret",
            OIDC_ALLOWED_ALGORITHMS="HS256",
            OIDC_TRANSACTION_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
            _env_file=None,
        )


def test_redis_backend_requires_a_valid_url():
    with pytest.raises(ValueError, match="REDIS_URL"):
        Settings(
            DATABASE_URL="sqlite:///test.db",
            SECRET_KEY="local-test-secret",
            RATE_LIMIT_BACKEND="redis",
            REDIS_URL="https://redis.example",
            RATE_LIMIT_KEY_SECRET="r" * 48,
            _env_file=None,
        )


def test_redis_backend_requires_a_dedicated_privacy_secret():
    redis_password = "validation-error-must-not-leak-this"
    with pytest.raises(ValueError, match="at least 32 bytes") as exc_info:
        Settings(
            DATABASE_URL="sqlite:///test.db",
            SECRET_KEY="local-test-secret",
            RATE_LIMIT_BACKEND="redis",
            REDIS_URL=f"redis://app:{redis_password}@localhost:6379/0",
            RATE_LIMIT_KEY_SECRET="too-short",
            _env_file=None,
        )

    assert redis_password not in str(exc_info.value)


def test_production_rejects_rate_limit_placeholder_secret():
    with pytest.raises(ValueError, match="must not use a placeholder"):
        Settings(
            DATABASE_URL="sqlite:///test.db",
            SECRET_KEY="a" * 48,
            ENVIRONMENT="production",
            RATE_LIMIT_BACKEND="redis",
            REDIS_URL="rediss://redis.example:6379/0",
            RATE_LIMIT_KEY_SECRET="generate_a_secure_random_rate_limit_key",
            _env_file=None,
        )


def test_rate_limit_numeric_settings_are_bounded():
    with pytest.raises(ValueError):
        Settings(
            DATABASE_URL="sqlite:///test.db",
            SECRET_KEY="local-test-secret",
            RATE_LIMIT_LIMIT=0,
            _env_file=None,
        )


def test_outbox_mode_requires_complete_secure_configuration():
    with pytest.raises(ValueError, match="OUTBOX_ENCRYPTION_KEY"):
        Settings(
            DATABASE_URL="sqlite:///test.db",
            SECRET_KEY="local-test-secret",
            EMAIL_DELIVERY_MODE="outbox",
            SMTP_HOST="smtp.example.com",
            SMTP_FROM="security@example.com",
            OUTBOX_ENCRYPTION_KEY="not-a-fernet-key",
            _env_file=None,
        )


def test_outbox_mode_accepts_valid_bounded_worker_settings():
    configured = Settings(
        DATABASE_URL="sqlite:///test.db",
        SECRET_KEY="local-test-secret",
        EMAIL_DELIVERY_MODE="outbox",
        SMTP_HOST="smtp.example.com",
        SMTP_FROM="security@example.com",
        OUTBOX_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
        OUTBOX_LEASE_SECONDS=20,
        SMTP_TIMEOUT_SECONDS=10,
        OUTBOX_SHUTDOWN_GRACE_SECONDS=10,
        _env_file=None,
    )

    assert configured.EMAIL_DELIVERY_MODE == "outbox"


def test_outbox_mode_rejects_unsafe_lease_and_backoff_settings():
    with pytest.raises(ValueError, match="BACKOFF_MAX"):
        Settings(
            DATABASE_URL="sqlite:///test.db",
            SECRET_KEY="local-test-secret",
            EMAIL_DELIVERY_MODE="outbox",
            SMTP_HOST="smtp.example.com",
            SMTP_FROM="security@example.com",
            OUTBOX_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"),
            OUTBOX_BACKOFF_BASE_SECONDS=30,
            OUTBOX_BACKOFF_MAX_SECONDS=10,
            _env_file=None,
        )
