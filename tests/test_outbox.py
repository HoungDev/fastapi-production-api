from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.account_action_token import AccountActionToken
from app.models.outbox_message import OutboxMessage
from app.models.user import User
from app.services.account_action_tokens import as_utc, utc_now
from app.services.email_verification import issue_email_verification_token
from app.services.outbox import (
    EMAIL_VERIFICATION_MESSAGE,
    PASSWORD_RESET_MESSAGE,
    decrypt_email_payload,
    enqueue_email_delivery,
    outbox_idempotency_key,
)


def _configure_outbox(monkeypatch) -> None:
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_MODE", "outbox")
    monkeypatch.setattr(
        settings,
        "OUTBOX_ENCRYPTION_KEY",
        SecretStr(Fernet.generate_key().decode("ascii")),
    )


def _register(email: str) -> int:
    username = f"outbox-user-{uuid4().hex}"
    response = TestClient(app).post(
        "/register/",
        json={"username": username, "password": "secret123", "email": email},
    )
    assert response.status_code == 200
    with SessionLocal() as db:
        return db.query(User).filter(User.username == username).one().id


def test_verification_request_commits_encrypted_outbox_message(monkeypatch):
    _configure_outbox(monkeypatch)
    email = f"outbox-verify-{uuid4().hex}@example.com"
    _register(email)

    response = TestClient(app).post(
        "/auth/email-verification/request",
        json={"email": email},
    )

    assert response.status_code == 202
    with SessionLocal() as db:
        token = (
            db.query(AccountActionToken)
            .filter(AccountActionToken.target == email)
            .one()
        )
        message = (
            db.query(OutboxMessage)
            .filter(OutboxMessage.message_type == EMAIL_VERIFICATION_MESSAGE)
            .order_by(OutboxMessage.created_at.desc())
            .first()
        )
        assert message is not None
        payload = decrypt_email_payload(message)
        assert payload["recipient"] == email
        assert token.token_hash != payload["token"]
        assert email.encode() not in message.payload_encrypted
        assert payload["token"].encode() not in message.payload_encrypted
        assert message.payload_expires_at == as_utc(token.expires_at)


def test_password_reset_request_commits_matching_outbox_message(monkeypatch):
    _configure_outbox(monkeypatch)
    email = f"outbox-reset-{uuid4().hex}@example.com"
    user_id = _register(email)
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).one()
        user.email_verified_at = datetime.now(UTC)
        db.commit()

    response = TestClient(app).post(
        "/auth/password-reset/request",
        json={"email": email},
    )

    assert response.status_code == 202
    with SessionLocal() as db:
        token = (
            db.query(AccountActionToken)
            .filter(AccountActionToken.target == email)
            .one()
        )
        message = (
            db.query(OutboxMessage)
            .filter(OutboxMessage.message_type == PASSWORD_RESET_MESSAGE)
            .order_by(OutboxMessage.created_at.desc())
            .first()
        )
        assert message is not None
        assert decrypt_email_payload(message)["recipient"] == email
        assert message.payload_expires_at == as_utc(token.expires_at)


def test_disabled_delivery_does_not_create_outbox(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_MODE", "disabled")
    email = f"outbox-disabled-{uuid4().hex}@example.com"
    _register(email)

    with SessionLocal() as db:
        before = db.query(OutboxMessage).count()
    response = TestClient(app).post(
        "/auth/email-verification/request",
        json={"email": email},
    )
    with SessionLocal() as db:
        after = db.query(OutboxMessage).count()

    assert response.status_code == 202
    assert after == before


def test_token_and_outbox_roll_back_together_when_commit_fails(monkeypatch):
    _configure_outbox(monkeypatch)
    email = f"outbox-rollback-{uuid4().hex}@example.com"
    _register(email)
    with SessionLocal() as count_db:
        outbox_count = count_db.query(OutboxMessage).count()
    db = SessionLocal()

    def fail_after_flush() -> None:
        db.flush()
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(db, "commit", fail_after_flush)
    try:
        with pytest.raises(RuntimeError, match="database unavailable"):
            issue_email_verification_token(email, db)
    finally:
        db.close()

    with SessionLocal() as verification_db:
        assert (
            verification_db.query(AccountActionToken)
            .filter(AccountActionToken.target == email)
            .count()
            == 0
        )
        assert verification_db.query(OutboxMessage).count() == outbox_count


def test_idempotency_key_rejects_duplicate_logical_enqueue(monkeypatch):
    _configure_outbox(monkeypatch)
    token_hash = "a" * 64
    idempotency_key = outbox_idempotency_key(EMAIL_VERIFICATION_MESSAGE, token_hash)
    expires_at = utc_now() + timedelta(minutes=5)
    with SessionLocal() as db:
        enqueue_email_delivery(
            db,
            message_type=EMAIL_VERIFICATION_MESSAGE,
            recipient="first@example.com",
            token="first-token",
            token_hash=token_hash,
            action_url="https://app.example.com/verify-email",
            expires_at=expires_at,
        )
        db.commit()

    with SessionLocal() as db:
        enqueue_email_delivery(
            db,
            message_type=EMAIL_VERIFICATION_MESSAGE,
            recipient="second@example.com",
            token="second-token",
            token_hash=token_hash,
            action_url="https://app.example.com/verify-email",
            expires_at=expires_at,
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    with SessionLocal() as db:
        assert (
            db.query(OutboxMessage)
            .filter(OutboxMessage.idempotency_key == idempotency_key)
            .count()
            == 1
        )
