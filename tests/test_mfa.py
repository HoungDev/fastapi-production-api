from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pyotp
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.auth.decode_token import decode_token
from app.auth.mfa import require_recent_mfa
from app.auth.refresh_token import hash_refresh_token
from app.auth.security import hash_password
from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.account_action_token import AccountActionToken
from app.models.mfa_recovery_code import MFARecoveryCode
from app.models.refresh_token import RefreshToken
from app.models.user import User

client = TestClient(app)
PASSWORD = "Mfa-test-password-123"


@pytest.fixture
def mfa_user(monkeypatch):
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "MFA_ENCRYPTION_KEY",
        SecretStr(Fernet.generate_key().decode("ascii")),
    )
    username = f"mfa-{uuid4().hex}"
    db = SessionLocal()
    user = User(
        username=username,
        email=f"{username}@example.com",
        password=hash_password(PASSWORD),
    )
    db.add(user)
    db.commit()
    user_id = user.id
    db.close()

    yield {"id": user_id, "username": username}

    db = SessionLocal()
    db.query(AccountActionToken).filter(AccountActionToken.user_id == user_id).delete()
    db.query(MFARecoveryCode).filter(MFARecoveryCode.user_id == user_id).delete()
    db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete()
    db.query(User).filter(User.id == user_id).delete()
    db.commit()
    db.close()


def _login(username: str, device: str = "Test laptop"):
    return client.post(
        "/login/",
        data={"username": username, "password": PASSWORD},
        headers={"X-Device-Name": device},
    )


def _bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _enroll(username: str) -> tuple[str, list[str], dict]:
    initial_login = _login(username)
    assert initial_login.status_code == 200
    initial_tokens = initial_login.json()
    headers = _bearer(initial_tokens["access_token"])

    enrollment = client.post(
        "/auth/mfa/totp/enroll",
        json={"password": PASSWORD},
        headers=headers,
    )
    assert enrollment.status_code == 200
    secret = enrollment.json()["secret"]
    assert "otpauth://totp/" in enrollment.json()["provisioning_uri"]

    previous_step = datetime.now(UTC) - timedelta(seconds=30)
    confirmation = client.post(
        "/auth/mfa/totp/confirm",
        json={"code": pyotp.TOTP(secret).at(previous_step)},
        headers=headers,
    )
    assert confirmation.status_code == 200
    recovery_codes = confirmation.json()["recovery_codes"]
    assert len(recovery_codes) == settings.MFA_RECOVERY_CODE_COUNT
    return secret, recovery_codes, initial_tokens


def test_totp_enrollment_stores_only_protected_secrets(mfa_user):
    secret, recovery_codes, _ = _enroll(mfa_user["username"])

    db = SessionLocal()
    user = db.query(User).filter(User.id == mfa_user["id"]).one()
    stored_codes = (
        db.query(MFARecoveryCode).filter(MFARecoveryCode.user_id == user.id).all()
    )
    assert user.mfa_enabled_at is not None
    assert user.mfa_secret_encrypted != secret
    assert secret not in user.mfa_secret_encrypted
    assert all(code.code_hash not in recovery_codes for code in stored_codes)
    assert all(len(code.code_hash) == 64 for code in stored_codes)
    db.close()

    access_token = _login(mfa_user["username"]).json().get("access_token")
    assert access_token is None


def test_mfa_login_challenge_is_single_use_and_marks_access_token(mfa_user):
    secret, _, _ = _enroll(mfa_user["username"])
    challenge_response = _login(mfa_user["username"], "Work laptop")
    assert challenge_response.status_code == 200
    challenge = challenge_response.json()
    assert challenge["mfa_required"] is True
    assert "access_token" not in challenge

    db = SessionLocal()
    stored = (
        db.query(AccountActionToken)
        .filter(AccountActionToken.user_id == mfa_user["id"])
        .order_by(AccountActionToken.id.desc())
        .first()
    )
    assert stored.token_hash != challenge["challenge_token"]
    assert stored.target == "Work laptop"
    db.close()

    current_code = pyotp.TOTP(secret).now()
    verification = client.post(
        "/auth/mfa/challenge/verify",
        json={
            "challenge_token": challenge["challenge_token"],
            "code": current_code,
        },
    )
    assert verification.status_code == 200
    tokens = verification.json()
    payload = decode_token(tokens["access_token"])
    assert set(payload.amr) == {"pwd", "otp"}
    assert payload.auth_time is not None
    assert require_recent_mfa(tokens["access_token"]).sub == mfa_user["username"]

    replay = client.post(
        "/auth/mfa/challenge/verify",
        json={
            "challenge_token": challenge["challenge_token"],
            "code": current_code,
        },
    )
    assert replay.status_code == 400

    fresh_challenge = _login(mfa_user["username"]).json()["challenge_token"]
    replayed_counter = client.post(
        "/auth/mfa/challenge/verify",
        json={"challenge_token": fresh_challenge, "code": current_code},
    )
    assert replayed_counter.status_code == 400

    refreshed = client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refreshed.status_code == 200
    refreshed_payload = decode_token(refreshed.json()["access_token"])
    assert refreshed_payload.amr == ["refresh"]
    assert refreshed_payload.auth_time is None
    with pytest.raises(HTTPException) as error:
        require_recent_mfa(refreshed.json()["access_token"])
    assert error.value.status_code == 403


def test_recovery_code_is_single_use_and_revokes_existing_sessions(mfa_user):
    _, recovery_codes, initial_tokens = _enroll(mfa_user["username"])
    challenge = _login(mfa_user["username"]).json()["challenge_token"]
    verification = client.post(
        "/auth/mfa/challenge/verify",
        json={"challenge_token": challenge, "code": recovery_codes[0]},
    )
    assert verification.status_code == 200
    payload = decode_token(verification.json()["access_token"])
    assert set(payload.amr) == {"pwd", "recovery"}
    with pytest.raises(HTTPException):
        require_recent_mfa(verification.json()["access_token"])

    db = SessionLocal()
    old_session = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token == hash_refresh_token(initial_tokens["refresh_token"])
        )
        .one()
    )
    assert old_session.revoked is True
    assert old_session.revocation_reason == "mfa_recovery_used"
    db.close()

    second_challenge = _login(mfa_user["username"]).json()["challenge_token"]
    reused = client.post(
        "/auth/mfa/challenge/verify",
        json={"challenge_token": second_challenge, "code": recovery_codes[0]},
    )
    assert reused.status_code == 400


def test_regenerate_codes_and_disable_mfa_revoke_sessions(mfa_user):
    secret, old_codes, initial_tokens = _enroll(mfa_user["username"])
    headers = _bearer(initial_tokens["access_token"])

    regenerated = client.post(
        "/auth/mfa/recovery-codes/regenerate",
        json={"password": PASSWORD, "code": pyotp.TOTP(secret).now()},
        headers=headers,
    )
    assert regenerated.status_code == 200
    new_codes = regenerated.json()["recovery_codes"]
    assert set(new_codes).isdisjoint(old_codes)

    disabled = client.post(
        "/auth/mfa/disable",
        json={"password": PASSWORD, "code": new_codes[0]},
        headers=headers,
    )
    assert disabled.status_code == 200
    assert disabled.json() == {"message": "MFA disabled"}

    status_response = client.get("/auth/mfa/status", headers=headers)
    assert status_response.json() == {
        "enabled": False,
        "recovery_codes_remaining": 0,
    }
    normal_login = _login(mfa_user["username"])
    assert normal_login.status_code == 200
    assert "access_token" in normal_login.json()


def test_mfa_rejects_invalid_credentials_and_unavailable_service(mfa_user):
    login = _login(mfa_user["username"])
    headers = _bearer(login.json()["access_token"])
    wrong_password = client.post(
        "/auth/mfa/totp/enroll",
        json={"password": "wrong-password"},
        headers=headers,
    )
    assert wrong_password.status_code == 401

    settings.MFA_ENABLED = False
    unavailable = client.post(
        "/auth/mfa/totp/enroll",
        json={"password": PASSWORD},
        headers=headers,
    )
    assert unavailable.status_code == 503
