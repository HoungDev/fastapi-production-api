from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.v1.email_verification import ACCEPTED_MESSAGE
from app.db.session import SessionLocal
from app.main import app
from app.models.account_action_token import AccountActionToken
from app.services.email_delivery import SMTPEmailSender, get_email_sender
from app.services.email_verification import (
    confirm_email_verification,
    hash_account_action_token,
    issue_email_verification_token,
)


class CapturingEmailSender:
    def __init__(self) -> None:
        self.deliveries: list[tuple[str, str]] = []

    def send_verification(self, recipient: str, token: str) -> None:
        self.deliveries.append((recipient, token))


def _register(email: str) -> str:
    username = f"email-user-{uuid4().hex}"
    response = TestClient(app).post(
        "/register/",
        json={"username": username, "password": "secret123", "email": email},
    )
    assert response.status_code == 200
    return response.json()["email"]


def test_registration_normalizes_optional_email():
    normalized_email = _register(f"Mixed.Case.{uuid4().hex}@Example.COM")

    assert normalized_email.endswith("@example.com")
    assert normalized_email == normalized_email.casefold()


def test_registration_remains_backward_compatible_without_email():
    response = TestClient(app).post(
        "/register/",
        json={
            "username": f"no-email-{uuid4().hex}",
            "password": "secret123",
        },
    )

    assert response.status_code == 200
    assert response.json()["email"] is None
    assert response.json()["email_verified_at"] is None


def test_duplicate_normalized_email_returns_conflict():
    local_part = f"duplicate-{uuid4().hex}"
    _register(f"{local_part}@Example.COM")

    response = TestClient(app).post(
        "/register/",
        json={
            "username": f"second-user-{uuid4().hex}",
            "password": "secret123",
            "email": f"{local_part}@example.com",
        },
    )

    assert response.status_code == 409


def test_malformed_email_is_rejected():
    response = TestClient(app).post(
        "/register/",
        json={
            "username": f"invalid-email-{uuid4().hex}",
            "password": "secret123",
            "email": "not-an-email",
        },
    )

    assert response.status_code == 422


def test_verification_is_single_use_and_only_hash_is_stored():
    email = _register(f"verify-{uuid4().hex}@example.com")
    sender = CapturingEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender

    try:
        client = TestClient(app)
        request_response = client.post(
            "/auth/email-verification/request", json={"email": email}
        )
        recipient, raw_token = sender.deliveries[0]

        assert request_response.status_code == 202
        assert request_response.json() == {"message": ACCEPTED_MESSAGE}
        assert recipient == email

        with SessionLocal() as db:
            stored = (
                db.query(AccountActionToken)
                .filter(
                    AccountActionToken.token_hash
                    == hash_account_action_token(raw_token)
                )
                .one()
            )
            assert stored.token_hash != raw_token

        assert (
            client.post(
                "/auth/email-verification/confirm", json={"token": raw_token}
            ).status_code
            == 200
        )
        replay = client.post(
            "/auth/email-verification/confirm", json={"token": raw_token}
        )
        assert replay.status_code == 400
    finally:
        app.dependency_overrides.pop(get_email_sender, None)


def test_resend_invalidates_previous_token():
    email = _register(f"resend-{uuid4().hex}@example.com")
    sender = CapturingEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender

    try:
        client = TestClient(app)
        for _ in range(2):
            assert (
                client.post(
                    "/auth/email-verification/request", json={"email": email}
                ).status_code
                == 202
            )

        old_token = sender.deliveries[0][1]
        new_token = sender.deliveries[1][1]
        assert old_token != new_token
        assert (
            client.post(
                "/auth/email-verification/confirm", json={"token": old_token}
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/auth/email-verification/confirm", json={"token": new_token}
            ).status_code
            == 200
        )
    finally:
        app.dependency_overrides.pop(get_email_sender, None)


def test_request_response_does_not_disclose_unknown_email():
    sender = CapturingEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender

    try:
        response = TestClient(app).post(
            "/auth/email-verification/request",
            json={"email": f"missing-{uuid4().hex}@example.com"},
        )
    finally:
        app.dependency_overrides.pop(get_email_sender, None)

    assert response.status_code == 202
    assert response.json() == {"message": ACCEPTED_MESSAGE}
    assert sender.deliveries == []


def test_expired_token_is_rejected():
    token = SimpleNamespace(
        consumed_at=None,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    query = MagicMock()
    query.filter.return_value.with_for_update.return_value.first.return_value = token
    db = MagicMock()
    db.query.return_value = query

    with pytest.raises(HTTPException, match="Invalid or expired") as exc_info:
        confirm_email_verification("a" * 43, db)

    assert exc_info.value.status_code == 400
    db.commit.assert_not_called()


def test_wrong_purpose_token_is_rejected_by_query():
    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None

    with pytest.raises(HTTPException, match="Invalid or expired"):
        confirm_email_verification("b" * 43, db)

    db.query.return_value.filter.assert_called_once()


def test_token_bound_to_another_email_is_rejected():
    stored_token = SimpleNamespace(
        user_id=123,
        target="old-email@example.com",
        consumed_at=None,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    user = SimpleNamespace(email="new-email@example.com", email_verified_at=None)
    token_query = MagicMock()
    token_query.filter.return_value.with_for_update.return_value.first.return_value = (
        stored_token
    )
    user_query = MagicMock()
    user_query.filter.return_value.first.return_value = user
    db = MagicMock()
    db.query.side_effect = [token_query, user_query]

    with pytest.raises(HTTPException, match="Invalid or expired"):
        confirm_email_verification("d" * 43, db)

    db.commit.assert_not_called()


def test_issuance_rolls_back_when_commit_fails():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        id=123,
        email="rollback@example.com",
        email_verified_at=None,
    )
    db.commit.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        issue_email_verification_token("rollback@example.com", db)

    db.rollback.assert_called_once_with()


def test_confirmation_rolls_back_when_commit_fails():
    stored_token = SimpleNamespace(
        user_id=123,
        target="rollback@example.com",
        consumed_at=None,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    user = SimpleNamespace(email="rollback@example.com", email_verified_at=None)
    token_query = MagicMock()
    token_query.filter.return_value.with_for_update.return_value.first.return_value = (
        stored_token
    )
    user_query = MagicMock()
    user_query.filter.return_value.first.return_value = user
    db = MagicMock()
    db.query.side_effect = [token_query, user_query]
    db.commit.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        confirm_email_verification("c" * 43, db)

    db.rollback.assert_called_once_with()


def test_delivery_failure_does_not_log_raw_token(caplog):
    email = _register(f"delivery-{uuid4().hex}@example.com")
    sender = MagicMock()
    sender.send_verification.side_effect = RuntimeError("provider unavailable")
    app.dependency_overrides[get_email_sender] = lambda: sender

    try:
        with caplog.at_level("ERROR"):
            response = TestClient(app).post(
                "/auth/email-verification/request", json={"email": email}
            )
    finally:
        app.dependency_overrides.pop(get_email_sender, None)

    raw_token = sender.send_verification.call_args.args[1]
    assert response.status_code == 202
    assert raw_token not in caplog.text


def test_disabled_delivery_does_not_issue_token():
    with patch(
        "app.api.v1.email_verification.issue_email_verification_token"
    ) as issue_token:
        response = TestClient(app).post(
            "/auth/email-verification/request",
            json={"email": f"disabled-{uuid4().hex}@example.com"},
        )

    assert response.status_code == 202
    issue_token.assert_not_called()


def test_smtp_sender_uses_tls_authentication_and_verification_url():
    smtp = MagicMock()
    smtp_context = MagicMock()
    smtp.__enter__.return_value = smtp_context

    with (
        patch("app.services.email_delivery.smtplib.SMTP", return_value=smtp),
        patch.multiple(
            "app.services.email_delivery.settings",
            SMTP_HOST="smtp.example.com",
            SMTP_PORT=587,
            SMTP_TIMEOUT_SECONDS=10,
            SMTP_STARTTLS=True,
            SMTP_USERNAME="mailer",
            SMTP_PASSWORD=SecretStr("secret"),
            SMTP_FROM="security@example.com",
            EMAIL_VERIFICATION_URL="https://app.example.com/verify-email",
        ),
    ):
        SMTPEmailSender().send_verification("user@example.com", "raw-token")

    smtp_context.starttls.assert_called_once_with()
    smtp_context.login.assert_called_once_with("mailer", "secret")
    message = smtp_context.send_message.call_args.args[0]
    assert message["To"] == "user@example.com"
    assert "https://app.example.com/verify-email?token=raw-token" in str(message)
