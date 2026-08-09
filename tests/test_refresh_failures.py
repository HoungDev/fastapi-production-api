from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.auth.refresh import refresh_access_token, revoke_refresh_token


def database_with_results(*results):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = results
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
    stored_token = SimpleNamespace(revoked=True)
    db = database_with_results(stored_token)

    with pytest.raises(HTTPException) as error:
        refresh_access_token("revoked-token", db)

    assert_unauthorized(error, "Refresh token revoked")


def test_refresh_rejects_expired_token():
    stored_token = SimpleNamespace(
        revoked=False,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
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
    )
    db = database_with_results(stored_token, None)

    with pytest.raises(HTTPException) as error:
        refresh_access_token("orphaned-token", db)

    assert_unauthorized(error, "User not found")


def test_refresh_rolls_back_when_rotation_commit_fails():
    stored_token = SimpleNamespace(
        revoked=False,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        user_id=123,
    )
    user = SimpleNamespace(id=123, username="houngdev")
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


def test_logout_rejects_unknown_token():
    db = database_with_results(None)

    with pytest.raises(HTTPException) as error:
        revoke_refresh_token("unknown-token", db)

    assert_unauthorized(error, "Invalid refresh token")


def test_logout_rolls_back_when_commit_fails():
    stored_token = SimpleNamespace(revoked=False)
    db = database_with_results(stored_token)
    db.commit.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        revoke_refresh_token("current-token", db)

    db.rollback.assert_called_once_with()
