from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.auth.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.refresh_token import RefreshToken
from app.models.user import User

client = TestClient(app)


def auth_headers(username: str) -> dict[str, str]:
    token = create_access_token({"sub": username})
    return {"Authorization": f"Bearer {token}"}


def create_user(role: str = "user") -> User:
    db = SessionLocal()
    try:
        user = User(
            username=f"admin_test_{uuid4().hex[:8]}",
            password=hash_password("secret123"),
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user
    finally:
        db.close()


def delete_user_if_present(user_id: int) -> None:
    db = SessionLocal()
    try:
        db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete()
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            db.delete(user)
            db.commit()
    finally:
        db.close()


def test_admin_endpoint_rejects_non_admin_user():
    user = create_user()

    try:
        response = client.get("/admin/test", headers=auth_headers(user.username))

        assert response.status_code == 403
        assert response.json() == {"detail": "Admin access required"}
    finally:
        delete_user_if_present(user.id)


def test_admin_can_manage_user_lifecycle():
    user = create_user()
    headers = auth_headers("houngdev")

    try:
        list_response = client.get("/admin/users", headers=headers)
        get_response = client.get(f"/admin/users/{user.id}", headers=headers)
        role_response = client.patch(
            f"/admin/users/{user.id}/role",
            headers=headers,
            json={"role": "admin"},
        )
        delete_response = client.delete(f"/admin/users/{user.id}", headers=headers)
        missing_response = client.get(f"/admin/users/{user.id}", headers=headers)
        missing_role_response = client.patch(
            f"/admin/users/{user.id}/role",
            headers=headers,
            json={"role": "admin"},
        )
        missing_delete_response = client.delete(
            f"/admin/users/{user.id}",
            headers=headers,
        )

        assert list_response.status_code == 200
        assert any(item["id"] == user.id for item in list_response.json())
        assert get_response.status_code == 200
        assert get_response.json()["username"] == user.username
        assert role_response.status_code == 200
        assert role_response.json()["role"] == "admin"
        assert delete_response.status_code == 200
        assert delete_response.json() == {"message": "User deleted successfully"}
        assert missing_response.status_code == 404
        assert missing_response.json() == {"detail": "User not found"}
        assert missing_role_response.status_code == 404
        assert missing_role_response.json() == {"detail": "User not found"}
        assert missing_delete_response.status_code == 404
        assert missing_delete_response.json() == {"detail": "User not found"}
    finally:
        delete_user_if_present(user.id)


def test_admin_disables_account_and_revokes_existing_authentication():
    user = create_user()
    admin_headers = auth_headers("houngdev")

    try:
        login_response = client.post(
            "/login/",
            data={"username": user.username, "password": "secret123"},
        )
        assert login_response.status_code == 200
        tokens = login_response.json()
        user_headers = {
            "Authorization": f"Bearer {tokens['access_token']}",
        }

        disable_response = client.patch(
            f"/admin/users/{user.id}/status",
            headers=admin_headers,
            json={"is_active": False},
        )

        assert disable_response.status_code == 200
        assert disable_response.json()["is_active"] is False
        assert client.get("/auth/me", headers=user_headers).status_code == 401

        disabled_login = client.post(
            "/login/",
            data={"username": user.username, "password": "secret123"},
        )
        assert disabled_login.status_code == 401
        assert disabled_login.json() == {"detail": "Invalid username or password"}

        refresh_response = client.post(
            "/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert refresh_response.status_code == 401

        db = SessionLocal()
        try:
            sessions = (
                db.query(RefreshToken).filter(RefreshToken.user_id == user.id).all()
            )
            assert sessions
            assert all(session.revoked for session in sessions)
            assert all(
                session.revocation_reason == "account_disabled" for session in sessions
            )
        finally:
            db.close()

        enable_response = client.patch(
            f"/admin/users/{user.id}/status",
            headers=admin_headers,
            json={"is_active": True},
        )
        assert enable_response.status_code == 200
        assert enable_response.json()["is_active"] is True

        new_login = client.post(
            "/login/",
            data={"username": user.username, "password": "secret123"},
        )
        assert new_login.status_code == 200

        missing_response = client.patch(
            "/admin/users/2147483647/status",
            headers=admin_headers,
            json={"is_active": False},
        )
        assert missing_response.status_code == 404
    finally:
        delete_user_if_present(user.id)
