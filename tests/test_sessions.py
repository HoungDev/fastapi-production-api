from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.refresh_token import hash_refresh_token, normalize_device_name
from app.db.session import SessionLocal
from app.main import app
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.sessions import revoke_all_user_sessions, revoke_session_family


def _login(
    device_name: str, *, username: str = "houngdev", password: str = "secret123"
):
    response = TestClient(app).post(
        "/login/",
        data={"username": username, "password": password},
        headers={"X-Device-Name": device_name},
    )
    assert response.status_code == 200
    return response.json()


def _authorization(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def test_login_creates_distinct_device_session_families():
    _login("  Work   Laptop  ")
    second = _login("Phone")

    response = TestClient(app).get(
        "/auth/sessions",
        headers=_authorization(second["access_token"]),
    )

    assert response.status_code == 200
    sessions = response.json()
    ids = {session["id"] for session in sessions}
    assert len(ids) >= 2
    assert all(str(UUID(session_id)) == session_id for session_id in ids)
    assert {"Work Laptop", "Phone"} <= {session["device_name"] for session in sessions}


def test_rotation_stays_in_family_and_replay_revokes_descendant():
    tokens = _login("Replay test")
    with SessionLocal() as db:
        old_record = (
            db.query(RefreshToken)
            .filter(RefreshToken.token == hash_refresh_token(tokens["refresh_token"]))
            .one()
        )
        family_id = old_record.family_id

    rotated = TestClient(app).post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert rotated.status_code == 200

    with SessionLocal() as db:
        new_record = (
            db.query(RefreshToken)
            .filter(
                RefreshToken.token
                == hash_refresh_token(rotated.json()["refresh_token"])
            )
            .one()
        )
        assert new_record.family_id == family_id
        assert new_record.revoked is False

    replay = TestClient(app).post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert replay.status_code == 401
    assert replay.json() == {"detail": "Invalid refresh token"}

    with SessionLocal() as db:
        new_record = (
            db.query(RefreshToken)
            .filter(
                RefreshToken.token
                == hash_refresh_token(rotated.json()["refresh_token"])
            )
            .one()
        )
        assert new_record.revoked is True
        assert new_record.revocation_reason == "reuse_detected"


def test_revoke_one_session_is_idempotent_and_isolated():
    first = _login("Session to revoke")
    second = _login("Session to keep")
    headers = _authorization(second["access_token"])
    sessions = TestClient(app).get("/auth/sessions", headers=headers).json()
    target = next(
        item for item in sessions if item["device_name"] == "Session to revoke"
    )

    for _ in range(2):
        response = TestClient(app).delete(
            f"/auth/sessions/{target['id']}", headers=headers
        )
        assert response.status_code == 200

    remaining = TestClient(app).get("/auth/sessions", headers=headers).json()
    assert target["id"] not in {item["id"] for item in remaining}
    assert any(item["device_name"] == "Session to keep" for item in remaining)
    assert first["refresh_token"] != second["refresh_token"]


def test_cross_user_cannot_revoke_another_users_session():
    owner_tokens = _login("Owner device")
    username = f"other-{uuid4().hex}"
    password = "OtherPassword123!"
    register = TestClient(app).post(
        "/register/",
        json={"username": username, "password": password},
    )
    assert register.status_code == 200
    other_tokens = _login("Other device", username=username, password=password)

    owner_sessions = (
        TestClient(app)
        .get(
            "/auth/sessions",
            headers=_authorization(owner_tokens["access_token"]),
        )
        .json()
    )
    owner_session = next(
        item for item in owner_sessions if item["device_name"] == "Owner device"
    )
    response = TestClient(app).delete(
        f"/auth/sessions/{owner_session['id']}",
        headers=_authorization(other_tokens["access_token"]),
    )

    assert response.status_code == 200
    still_active = TestClient(app).post(
        "/auth/refresh",
        json={"refresh_token": owner_tokens["refresh_token"]},
    )
    assert still_active.status_code == 200


def test_revoke_all_sessions_and_logout_revoke_families():
    first = _login("All one")
    second = _login("All two")
    headers = _authorization(second["access_token"])

    response = TestClient(app).delete("/auth/sessions", headers=headers)
    assert response.status_code == 200
    assert TestClient(app).get("/auth/sessions", headers=headers).json() == []
    for token in (first["refresh_token"], second["refresh_token"]):
        assert (
            TestClient(app)
            .post("/auth/refresh", json={"refresh_token": token})
            .status_code
            == 401
        )

    logout_tokens = _login("Logout family")
    rotated = (
        TestClient(app)
        .post("/auth/refresh", json={"refresh_token": logout_tokens["refresh_token"]})
        .json()
    )
    assert (
        TestClient(app)
        .post("/auth/logout", json={"refresh_token": rotated["refresh_token"]})
        .status_code
        == 200
    )

    with SessionLocal() as db:
        record = (
            db.query(RefreshToken)
            .filter(RefreshToken.token == hash_refresh_token(rotated["refresh_token"]))
            .one()
        )
        assert all(
            item.revoked
            for item in db.query(RefreshToken)
            .filter(RefreshToken.family_id == record.family_id)
            .all()
        )


def test_session_listing_omits_expired_families():
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "houngdev").one()
        db.add(
            RefreshToken(
                user_id=user.id,
                token=hash_refresh_token(f"expired-{uuid4().hex}"),
                expires_at=datetime.now(UTC) - timedelta(minutes=1),
                device_name="Expired device",
            )
        )
        db.commit()

    tokens = _login("Active listing device")
    sessions = (
        TestClient(app)
        .get("/auth/sessions", headers=_authorization(tokens["access_token"]))
        .json()
    )
    assert "Expired device" not in {item["device_name"] for item in sessions}


def test_device_name_is_bounded_and_sanitized():
    assert normalize_device_name("  Work\nLaptop  ", None) == "Work Laptop"
    assert len(normalize_device_name("x" * 200, None)) == 100
    assert normalize_device_name(None, None) == "Unknown device"


@pytest.mark.parametrize(
    "operation",
    [revoke_session_family, revoke_all_user_sessions],
)
def test_session_revocation_rolls_back_on_database_failure(operation):
    db = MagicMock()
    db.commit.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        if operation is revoke_session_family:
            operation(123, str(uuid4()), db)
        else:
            operation(123, db)

    db.rollback.assert_called_once_with()
