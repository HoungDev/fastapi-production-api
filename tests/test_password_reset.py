from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v1.password_reset import ACCEPTED_MESSAGE
from app.db.session import SessionLocal
from app.main import app
from app.models.account_action_token import AccountActionToken
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.account_action_tokens import hash_account_action_token
from app.services.email_delivery import get_email_sender
from app.services.password_reset import (
    confirm_password_reset,
    issue_password_reset_token,
)

OLD_PASSWORD = "OldPassword123!"
NEW_PASSWORD = "NewPassword456!"


class CapturingEmailSender:
    def __init__(self) -> None:
        self.deliveries: list[tuple[str, str]] = []

    def send_password_reset(self, recipient: str, token: str) -> None:
        self.deliveries.append((recipient, token))


def _create_user(*, verified: bool = True, active: bool = True) -> tuple[int, str, str]:
    username = f"reset-user-{uuid4().hex}"
    email = f"reset-{uuid4().hex}@example.com"
    response = TestClient(app).post(
        "/register/",
        json={"username": username, "password": OLD_PASSWORD, "email": email},
    )
    assert response.status_code == 200

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).one()
        if verified:
            user.email_verified_at = datetime.now(UTC)
        user.is_active = active
        db.commit()
        return user.id, username, email


def _request_token(email: str, sender: CapturingEmailSender) -> str:
    response = TestClient(app).post(
        "/auth/password-reset/request",
        json={"email": email},
    )
    assert response.status_code == 202
    assert response.json() == {"message": ACCEPTED_MESSAGE}
    return sender.deliveries[-1][1]


def test_password_reset_revokes_refresh_sessions_and_changes_password():
    user_id, username, email = _create_user()
    login = TestClient(app).post(
        "/login/",
        data={"username": username, "password": OLD_PASSWORD},
    )
    assert login.status_code == 200
    old_refresh_token = login.json()["refresh_token"]

    sender = CapturingEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    try:
        raw_token = _request_token(email, sender)
        response = TestClient(app).post(
            "/auth/password-reset/confirm",
            json={"token": raw_token, "new_password": NEW_PASSWORD},
        )
    finally:
        app.dependency_overrides.pop(get_email_sender, None)

    assert response.status_code == 200
    with SessionLocal() as db:
        stored_token = (
            db.query(AccountActionToken)
            .filter(
                AccountActionToken.token_hash == hash_account_action_token(raw_token)
            )
            .one()
        )
        assert stored_token.token_hash != raw_token
        assert stored_token.consumed_at is not None
        assert all(
            item.revoked
            for item in db.query(RefreshToken)
            .filter(RefreshToken.user_id == user_id)
            .all()
        )

    revoked = TestClient(app).post(
        "/auth/refresh", json={"refresh_token": old_refresh_token}
    )
    assert revoked.status_code == 401
    assert (
        TestClient(app)
        .post("/login/", data={"username": username, "password": OLD_PASSWORD})
        .status_code
        == 401
    )
    assert (
        TestClient(app)
        .post("/login/", data={"username": username, "password": NEW_PASSWORD})
        .status_code
        == 200
    )


def test_password_reset_request_does_not_disclose_ineligible_accounts():
    _, _, unverified_email = _create_user(verified=False)
    _, _, inactive_email = _create_user(active=False)
    unknown_email = f"unknown-{uuid4().hex}@example.com"
    sender = CapturingEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender

    try:
        responses = [
            TestClient(app).post("/auth/password-reset/request", json={"email": email})
            for email in (unknown_email, unverified_email, inactive_email)
        ]
    finally:
        app.dependency_overrides.pop(get_email_sender, None)

    assert all(response.status_code == 202 for response in responses)
    assert all(
        response.json() == {"message": ACCEPTED_MESSAGE} for response in responses
    )
    assert sender.deliveries == []


def test_password_reset_resend_invalidates_previous_token():
    _, _, email = _create_user()
    sender = CapturingEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender

    try:
        old_token = _request_token(email, sender)
        new_token = _request_token(email, sender)
        old_response = TestClient(app).post(
            "/auth/password-reset/confirm",
            json={"token": old_token, "new_password": NEW_PASSWORD},
        )
        new_response = TestClient(app).post(
            "/auth/password-reset/confirm",
            json={"token": new_token, "new_password": NEW_PASSWORD},
        )
    finally:
        app.dependency_overrides.pop(get_email_sender, None)

    assert old_response.status_code == 400
    assert new_response.status_code == 200


def test_expired_password_reset_token_is_rejected():
    token = SimpleNamespace(
        consumed_at=None,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    query = MagicMock()
    query.filter.return_value.with_for_update.return_value.first.return_value = token
    db = MagicMock()
    db.query.return_value = query

    with pytest.raises(HTTPException, match="Invalid or expired") as exc_info:
        confirm_password_reset("a" * 43, NEW_PASSWORD, db)

    assert exc_info.value.status_code == 400
    db.commit.assert_not_called()


def test_wrong_purpose_password_reset_token_is_rejected():
    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None

    with pytest.raises(HTTPException, match="Invalid or expired"):
        confirm_password_reset("b" * 43, NEW_PASSWORD, db)

    db.query.return_value.filter.assert_called_once()


def test_password_reset_token_bound_to_old_email_is_rejected():
    stored_token = SimpleNamespace(
        user_id=123,
        target="old-email@example.com",
        consumed_at=None,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    user = SimpleNamespace(
        id=123,
        email="new-email@example.com",
        email_verified_at=datetime.now(UTC),
        is_active=True,
    )
    token_query = MagicMock()
    token_query.filter.return_value.with_for_update.return_value.first.return_value = (
        stored_token
    )
    user_query = MagicMock()
    user_query.filter.return_value.with_for_update.return_value.first.return_value = (
        user
    )
    db = MagicMock()
    db.query.side_effect = [token_query, user_query]

    with pytest.raises(HTTPException, match="Invalid or expired"):
        confirm_password_reset("c" * 43, NEW_PASSWORD, db)

    db.commit.assert_not_called()


@pytest.mark.parametrize(
    "new_password",
    ["too-short", "x" * 73],
)
def test_password_reset_rejects_password_outside_policy(new_password: str):
    response = TestClient(app).post(
        "/auth/password-reset/confirm",
        json={"token": "d" * 43, "new_password": new_password},
    )

    assert response.status_code == 422


def test_password_reset_issuance_rolls_back_when_commit_fails():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        id=123,
        email="rollback@example.com",
        email_verified_at=datetime.now(UTC),
        is_active=True,
    )
    db.commit.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        issue_password_reset_token("rollback@example.com", db)

    db.rollback.assert_called_once_with()


def test_password_reset_confirmation_rolls_back_when_commit_fails():
    stored_token = SimpleNamespace(
        user_id=123,
        target="rollback@example.com",
        consumed_at=None,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    user = SimpleNamespace(
        id=123,
        email="rollback@example.com",
        email_verified_at=datetime.now(UTC),
        is_active=True,
        password="old-hash",
    )
    token_query = MagicMock()
    token_query.filter.return_value.with_for_update.return_value.first.return_value = (
        stored_token
    )
    user_query = MagicMock()
    user_query.filter.return_value.with_for_update.return_value.first.return_value = (
        user
    )
    db = MagicMock()
    db.query.side_effect = [token_query, user_query]
    db.commit.side_effect = RuntimeError("database unavailable")

    with (
        patch("app.services.password_reset.hash_password", return_value="new-hash"),
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        confirm_password_reset("e" * 43, NEW_PASSWORD, db)

    db.rollback.assert_called_once_with()
    assert db.execute.call_count == 2


def test_password_reset_delivery_failure_does_not_log_raw_token(caplog):
    _, _, email = _create_user()
    sender = MagicMock()
    sender.send_password_reset.side_effect = RuntimeError("provider unavailable")
    app.dependency_overrides[get_email_sender] = lambda: sender

    try:
        with caplog.at_level("ERROR"):
            response = TestClient(app).post(
                "/auth/password-reset/request", json={"email": email}
            )
    finally:
        app.dependency_overrides.pop(get_email_sender, None)

    raw_token = sender.send_password_reset.call_args.args[1]
    assert response.status_code == 202
    assert raw_token not in caplog.text


def test_disabled_delivery_does_not_issue_password_reset_token():
    with patch("app.api.v1.password_reset.issue_password_reset_token") as issue_token:
        response = TestClient(app).post(
            "/auth/password-reset/request",
            json={"email": f"disabled-{uuid4().hex}@example.com"},
        )

    assert response.status_code == 202
    issue_token.assert_not_called()
