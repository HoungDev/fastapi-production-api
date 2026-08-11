from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.auth.refresh import refresh_access_token, revoke_refresh_token


def database_with_results(*results):
    db = MagicMock()
    queries = []
    for result in results:
        query = MagicMock()
        query.filter.return_value.first.return_value = result
        query.filter.return_value.with_for_update.return_value.first.return_value = (
            result
        )
        queries.append(query)
    db.query.side_effect = queries
    db.query_mocks = queries
    return db


def assert_unauthorized(error: pytest.ExceptionInfo[HTTPException], detail: str):
    assert error.value.status_code == 401
    assert error.value.detail == detail


def test_refresh_rejects_unknown_token():
    db = database_with_results(None)

    with pytest.raises(HTTPException) as error:
        refresh_access_token("unknown-token", db)

    assert_unauthorized(error, "Invalid refresh token")


def test_refresh_rejects_revoked_token():
    stored_token = SimpleNamespace(revoked=True, family_id="family-1")
    db = database_with_results(stored_token)

    with pytest.raises(HTTPException) as error:
        refresh_access_token("revoked-token", db)

    assert_unauthorized(error, "Invalid refresh token")
    db.commit.assert_called_once_with()


def test_refresh_replay_rolls_back_when_family_revocation_fails():
    stored_token = SimpleNamespace(revoked=True, family_id="family-1")
    db = database_with_results(stored_token)
    db.commit.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        refresh_access_token("replayed-token", db)

    db.rollback.assert_called_once_with()


def test_refresh_rejects_expired_token():
    stored_token = SimpleNamespace(
        revoked=False,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        family_id="family-1",
    )
    db = database_with_results(stored_token)

    with pytest.raises(HTTPException) as error:
        refresh_access_token("expired-token", db)

    assert_unauthorized(error, "Refresh token expired")


def test_refresh_rejects_token_for_missing_user():
    stored_token = SimpleNamespace(
        revoked=False,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        user_id=123,
        family_id="family-1",
    )
    db = database_with_results(stored_token, None)

    with pytest.raises(HTTPException) as error:
        refresh_access_token("orphaned-token", db)

    assert_unauthorized(error, "User not found")


def test_refresh_rejects_inactive_user_and_revokes_sessions():
    stored_token = SimpleNamespace(
        revoked=False,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        user_id=123,
        family_id="family-1",
    )
    user = SimpleNamespace(id=123, username="houngdev", is_active=False)
    db = database_with_results(stored_token, user)

    with pytest.raises(HTTPException) as error:
        refresh_access_token("inactive-user-token", db)

    assert_unauthorized(error, "Invalid refresh token")
    db.execute.assert_called_once()
    db.commit.assert_called_once_with()


def test_refresh_rolls_back_when_rotation_commit_fails():
    stored_token = SimpleNamespace(
        revoked=False,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        user_id=123,
        family_id="family-1",
        device_name="Test device",
    )
    user = SimpleNamespace(id=123, username="houngdev", is_active=True)
    db = database_with_results(stored_token, user)
    db.commit.side_effect = RuntimeError("database unavailable")

    with (
        patch(
            "app.auth.refresh.create_refresh_token",
            return_value=(
                "new-refresh-token",
                datetime.now(UTC) + timedelta(days=7),
            ),
        ),
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        refresh_access_token("current-token", db)

    db.rollback.assert_called_once_with()
    db.query_mocks[0].filter.return_value.with_for_update.assert_called_once_with()


def test_logout_rejects_unknown_token():
    db = database_with_results(None)

    with pytest.raises(HTTPException) as error:
        revoke_refresh_token("unknown-token", db)

    assert_unauthorized(error, "Invalid refresh token")


def test_logout_rolls_back_when_commit_fails():
    stored_token = SimpleNamespace(revoked=False, family_id="family-1")
    db = database_with_results(stored_token)
    db.commit.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        revoke_refresh_token("current-token", db)

    db.rollback.assert_called_once_with()
