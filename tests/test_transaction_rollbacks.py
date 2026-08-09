from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.auth.login import login
from app.auth.register import register
from app.core.config import settings
from app.schemas.user import UserCreate
from app.services.mfa import begin_totp_enrollment, issue_mfa_login_challenge
from app.services.oidc import begin_oidc_authorization
from app.services.oidc_provider import OIDCMetadata


def test_registration_rolls_back_when_commit_fails():
    db = MagicMock()
    db.commit.side_effect = RuntimeError("database unavailable")
    user = UserCreate(username="new-user", password="secret123")

    with (
        patch("app.auth.register.hash_password", return_value="hashed-password"),
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        register(user, db)

    db.rollback.assert_called_once_with()
    db.refresh.assert_not_called()


def test_registration_returns_conflict_for_duplicate_identity():
    from fastapi import HTTPException
    from sqlalchemy.exc import IntegrityError

    db = MagicMock()
    db.commit.side_effect = IntegrityError("insert", {}, Exception("duplicate"))
    user = UserCreate(
        username="duplicate-user",
        password="secret123",
        email="duplicate@example.com",
    )

    with (
        patch("app.auth.register.hash_password", return_value="hashed-password"),
        pytest.raises(HTTPException) as exc_info,
    ):
        register(user, db)

    assert exc_info.value.status_code == 409
    db.rollback.assert_called_once_with()


def test_login_rolls_back_when_refresh_token_commit_fails():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        id=123,
        username="houngdev",
        password="hashed-password",
        password_login_enabled=True,
        mfa_enabled_at=None,
    )
    db.commit.side_effect = RuntimeError("database unavailable")
    form_data = SimpleNamespace(username="houngdev", password="secret123")

    with (
        patch("app.auth.login.verify_password", return_value=True),
        patch("app.auth.login.prepare_session_tokens"),
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        login(form_data, db, "Test device")

    db.rollback.assert_called_once_with()


def test_mfa_challenge_rolls_back_when_commit_fails(monkeypatch):
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "MFA_ENCRYPTION_KEY",
        SecretStr(Fernet.generate_key().decode("ascii")),
    )
    db = MagicMock()
    db.commit.side_effect = RuntimeError("database unavailable")
    user = SimpleNamespace(id=123)

    with pytest.raises(RuntimeError, match="database unavailable"):
        issue_mfa_login_challenge(user, "Test device", db)

    db.rollback.assert_called_once_with()


def test_mfa_enrollment_rolls_back_when_commit_fails(monkeypatch):
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "MFA_ENCRYPTION_KEY",
        SecretStr(Fernet.generate_key().decode("ascii")),
    )
    user = SimpleNamespace(
        id=123,
        username="houngdev",
        email="houngdev@example.com",
        password="hashed-password",
        is_active=True,
        mfa_enabled_at=None,
        mfa_secret_encrypted=None,
        mfa_enrollment_created_at=None,
        mfa_last_counter=None,
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = user
    db.commit.side_effect = RuntimeError("database unavailable")

    with (
        patch("app.services.mfa.verify_password", return_value=True),
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        begin_totp_enrollment(user.id, "password", db)

    db.rollback.assert_called_once_with()


def test_oidc_authorization_rolls_back_when_commit_fails(monkeypatch):
    monkeypatch.setattr(settings, "OIDC_ENABLED", True)
    monkeypatch.setattr(settings, "OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setattr(settings, "OIDC_CLIENT_ID", "client-id")
    monkeypatch.setattr(
        settings,
        "OIDC_TRANSACTION_ENCRYPTION_KEY",
        SecretStr(Fernet.generate_key().decode("ascii")),
    )
    provider = MagicMock()
    provider.discover.return_value = OIDCMetadata(
        issuer="https://issuer.example",
        authorization_endpoint="https://issuer.example/authorize",
        token_endpoint="https://issuer.example/token",
        jwks_uri="https://issuer.example/jwks",
    )
    db = MagicMock()
    db.commit.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        begin_oidc_authorization(
            db,
            provider,
            intent="login",
            device_name="Test device",
        )

    db.rollback.assert_called_once_with()
