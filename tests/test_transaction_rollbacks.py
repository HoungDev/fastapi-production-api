from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.auth.login import login
from app.auth.register import register
from app.schemas.user import UserCreate


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
    )
    db.commit.side_effect = RuntimeError("database unavailable")
    form_data = SimpleNamespace(username="houngdev", password="secret123")

    with (
        patch("app.auth.login.verify_password", return_value=True),
        patch("app.auth.login.create_access_token", return_value="access-token"),
        patch(
            "app.auth.login.create_refresh_token",
            return_value=("refresh-token", MagicMock()),
        ),
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        login(form_data, db, "Test device")

    db.rollback.assert_called_once_with()
