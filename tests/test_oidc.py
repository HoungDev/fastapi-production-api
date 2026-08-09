import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import jwt
import pyotp
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
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
from app.models.external_identity import ExternalIdentity
from app.models.mfa_recovery_code import MFARecoveryCode
from app.models.oidc_transaction import OIDCTransaction
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.oidc import BROWSER_COOKIE_NAME, complete_oidc_authorization
from app.services.oidc_provider import (
    OIDCMetadata,
    OIDCProviderClient,
    OIDCProviderError,
    get_oidc_provider_client,
)

PASSWORD = "Oidc-test-password-123"


class FakeOIDCProvider:
    def __init__(self, issuer: str):
        self.metadata = OIDCMetadata(
            issuer=issuer,
            authorization_endpoint=f"{issuer}/authorize",
            token_endpoint=f"{issuer}/token",
            jwks_uri=f"{issuer}/jwks",
        )
        self.claims: dict = {}
        self.exchange_calls: list[dict] = []
        self.failure: Exception | None = None

    def discover(self):
        if self.failure:
            raise self.failure
        return self.metadata

    def exchange_code(self, metadata, **kwargs):
        self.exchange_calls.append(kwargs)
        if self.failure:
            raise self.failure
        return "signed-id-token"

    def validate_id_token(self, metadata, id_token):
        if self.failure:
            raise self.failure
        return self.claims.copy()


@dataclass
class OIDCTestContext:
    client: TestClient
    provider: FakeOIDCProvider
    issuer: str
    user_ids: list[int] = field(default_factory=list)


@pytest.fixture
def oidc_context(monkeypatch):
    issuer = f"https://issuer-{uuid4().hex}.example"
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(settings, "OIDC_ENABLED", True)
    monkeypatch.setattr(settings, "OIDC_ISSUER", issuer)
    monkeypatch.setattr(settings, "OIDC_CLIENT_ID", "test-client")
    monkeypatch.setattr(settings, "OIDC_CLIENT_SECRET", SecretStr("test-secret"))
    monkeypatch.setattr(
        settings,
        "OIDC_REDIRECT_URI",
        "http://testserver/auth/oidc/callback",
    )
    monkeypatch.setattr(
        settings,
        "OIDC_TRANSACTION_ENCRYPTION_KEY",
        SecretStr(key),
    )
    provider = FakeOIDCProvider(issuer)
    app.dependency_overrides[get_oidc_provider_client] = lambda: provider
    context = OIDCTestContext(
        client=TestClient(app, follow_redirects=False),
        provider=provider,
        issuer=issuer,
    )
    yield context
    app.dependency_overrides.pop(get_oidc_provider_client, None)

    db = SessionLocal()
    identity_user_ids = [
        value
        for (value,) in db.query(ExternalIdentity.user_id)
        .filter(ExternalIdentity.issuer == issuer)
        .all()
    ]
    user_ids = set(context.user_ids + identity_user_ids)
    db.query(OIDCTransaction).filter(OIDCTransaction.issuer == issuer).delete()
    db.query(ExternalIdentity).filter(ExternalIdentity.issuer == issuer).delete()
    if user_ids:
        db.query(AccountActionToken).filter(
            AccountActionToken.user_id.in_(user_ids)
        ).delete(synchronize_session=False)
        db.query(MFARecoveryCode).filter(MFARecoveryCode.user_id.in_(user_ids)).delete(
            synchronize_session=False
        )
        db.query(RefreshToken).filter(RefreshToken.user_id.in_(user_ids)).delete(
            synchronize_session=False
        )
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    db.commit()
    db.close()


def _create_user(context: OIDCTestContext, *, email: str | None = None) -> User:
    db = SessionLocal()
    username = f"oidc-local-{uuid4().hex}"
    user = User(
        username=username,
        email=email,
        email_verified_at=datetime.now(UTC) if email else None,
        password=hash_password(PASSWORD),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    context.user_ids.append(user.id)
    db.expunge(user)
    db.close()
    return user


def _password_login(context: OIDCTestContext, username: str):
    response = context.client.post(
        "/login/",
        data={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()


def _start(context: OIDCTestContext, path: str = "/auth/oidc/authorize", **kwargs):
    response = context.client.request(
        "POST" if "/link/" in path else "GET",
        path,
        follow_redirects=False,
        **kwargs,
    )
    assert response.status_code == 303
    parameters = parse_qs(urlsplit(response.headers["location"]).query)
    binding = response.cookies.get(BROWSER_COOKIE_NAME)
    assert binding
    return response, parameters, binding


def _set_claims(context: OIDCTestContext, parameters: dict, **overrides):
    context.provider.claims = {
        "iss": context.issuer,
        "sub": "provider-subject",
        "aud": "test-client",
        "nonce": parameters["nonce"][0],
        "email": "new-oidc-user@example.com",
        "email_verified": True,
        **overrides,
    }


def _callback(context: OIDCTestContext, parameters: dict):
    return context.client.get(
        "/auth/oidc/callback",
        params={"state": parameters["state"][0], "code": "provider-code"},
        follow_redirects=False,
    )


def test_oidc_login_uses_pkce_and_provisions_verified_identity(oidc_context):
    response, parameters, binding = _start(oidc_context)
    assert parameters["response_type"] == ["code"]
    assert parameters["code_challenge_method"] == ["S256"]
    assert len(parameters["code_challenge"][0]) == 43
    assert parameters["redirect_uri"] == [settings.OIDC_REDIRECT_URI]
    assert "openid" in parameters["scope"][0].split()

    db = SessionLocal()
    transaction = (
        db.query(OIDCTransaction)
        .filter(OIDCTransaction.issuer == oidc_context.issuer)
        .one()
    )
    assert transaction.state_hash != parameters["state"][0]
    assert transaction.nonce_hash != parameters["nonce"][0]
    assert transaction.browser_binding_hash != binding
    encrypted_verifier = transaction.code_verifier_encrypted
    db.close()

    _set_claims(oidc_context, parameters)
    callback = _callback(oidc_context, parameters)
    assert callback.status_code == 200
    tokens = callback.json()
    payload = decode_token(tokens["access_token"])
    assert payload.amr == ["oidc"]
    assert payload.auth_time is not None
    assert (
        oidc_context.provider.exchange_calls[0]["redirect_uri"]
        == settings.OIDC_REDIRECT_URI
    )
    verifier = oidc_context.provider.exchange_calls[0]["code_verifier"]
    assert 43 <= len(verifier) <= 128
    assert verifier not in encrypted_verifier

    db = SessionLocal()
    identity = (
        db.query(ExternalIdentity)
        .filter(ExternalIdentity.issuer == oidc_context.issuer)
        .one()
    )
    user = db.query(User).filter(User.id == identity.user_id).one()
    oidc_context.user_ids.append(user.id)
    assert identity.subject == "provider-subject"
    assert user.email == "new-oidc-user@example.com"
    assert user.email_verified_at is not None
    assert user.password_login_enabled is False
    identity_id = identity.id
    db.close()

    password_login = oidc_context.client.post(
        "/login/",
        data={"username": user.username, "password": PASSWORD},
    )
    assert password_login.status_code == 401

    cannot_unlink = oidc_context.client.delete(
        f"/auth/oidc/identities/{identity_id}",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert cannot_unlink.status_code == 409


def test_oidc_state_binding_nonce_expiry_and_replay_are_rejected(oidc_context):
    _, parameters, binding = _start(oidc_context)
    _set_claims(oidc_context, parameters)

    db = SessionLocal()
    with pytest.raises(HTTPException) as wrong_binding:
        complete_oidc_authorization(
            parameters["state"][0],
            "provider-code",
            "wrong-browser",
            db,
            oidc_context.provider,
        )
    assert wrong_binding.value.status_code == 400
    db.close()

    oidc_context.provider.claims["nonce"] = "wrong-nonce"
    bad_nonce = _callback(oidc_context, parameters)
    assert bad_nonce.status_code == 400

    oidc_context.provider.claims["nonce"] = parameters["nonce"][0]
    accepted = _callback(oidc_context, parameters)
    assert accepted.status_code == 200
    replay_client = TestClient(app, follow_redirects=False)
    replay_client.cookies.set(BROWSER_COOKIE_NAME, binding, path="/auth/oidc/callback")
    replay = replay_client.get(
        "/auth/oidc/callback",
        params={"state": parameters["state"][0], "code": "provider-code"},
    )
    assert replay.status_code == 400

    _, expired_parameters, _ = _start(oidc_context)
    db = SessionLocal()
    expired = (
        db.query(OIDCTransaction)
        .filter(
            OIDCTransaction.state_hash == hashlib_sha256(expired_parameters["state"][0])
        )
        .order_by(OIDCTransaction.id.desc())
        .first()
    )
    expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    db.close()
    _set_claims(oidc_context, expired_parameters)
    assert _callback(oidc_context, expired_parameters).status_code == 400


def hashlib_sha256(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def test_oidc_never_auto_links_by_matching_email(oidc_context):
    local = _create_user(oidc_context, email="collision@example.com")
    _, parameters, _ = _start(oidc_context)
    _set_claims(
        oidc_context,
        parameters,
        sub="different-subject",
        email="collision@example.com",
    )
    response = _callback(oidc_context, parameters)
    assert response.status_code == 409

    db = SessionLocal()
    assert (
        db.query(ExternalIdentity).filter(ExternalIdentity.user_id == local.id).count()
        == 0
    )
    db.close()


def test_explicit_link_list_and_unlink_revoke_refresh_sessions(oidc_context):
    local = _create_user(oidc_context)
    tokens = _password_login(oidc_context, local.username)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    _, parameters, _ = _start(
        oidc_context,
        "/auth/oidc/link/authorize",
        headers=headers,
    )
    _set_claims(
        oidc_context,
        parameters,
        sub="linked-subject",
        email="unverified@example.com",
        email_verified=False,
    )
    linked = _callback(oidc_context, parameters)
    assert linked.status_code == 200
    identity_id = linked.json()["identity"]["id"]
    assert linked.json()["identity"]["email"] is None

    listed = oidc_context.client.get("/auth/oidc/identities", headers=headers)
    assert [identity["id"] for identity in listed.json()] == [identity_id]

    db = SessionLocal()
    session = (
        db.query(RefreshToken)
        .filter(RefreshToken.token == hash_refresh_token(tokens["refresh_token"]))
        .one()
    )
    assert session.revoked is True
    assert session.revocation_reason == "external_identity_linked"
    db.close()

    unlinked = oidc_context.client.delete(
        f"/auth/oidc/identities/{identity_id}", headers=headers
    )
    assert unlinked.status_code == 200
    assert (
        oidc_context.client.get("/auth/oidc/identities", headers=headers).json() == []
    )


def test_refresh_issued_access_token_cannot_start_account_link(oidc_context):
    local = _create_user(oidc_context)
    tokens = _password_login(oidc_context, local.username)
    refreshed = oidc_context.client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    ).json()
    response = oidc_context.client.post(
        "/auth/oidc/link/authorize",
        headers={"Authorization": f"Bearer {refreshed['access_token']}"},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_oidc_login_preserves_local_mfa_requirement(oidc_context, monkeypatch):
    local = _create_user(oidc_context)
    mfa_key = Fernet.generate_key()
    secret = pyotp.random_base32()
    monkeypatch.setattr(settings, "MFA_ENABLED", True)
    monkeypatch.setattr(
        settings, "MFA_ENCRYPTION_KEY", SecretStr(mfa_key.decode("ascii"))
    )
    db = SessionLocal()
    user = db.query(User).filter(User.id == local.id).one()
    user.mfa_secret_encrypted = Fernet(mfa_key).encrypt(secret.encode()).decode()
    user.mfa_enabled_at = datetime.now(UTC)
    identity = ExternalIdentity(
        user_id=user.id,
        issuer=oidc_context.issuer,
        subject="mfa-subject",
        email="mfa@example.com",
    )
    db.add(identity)
    db.commit()
    db.close()

    _, parameters, _ = _start(oidc_context)
    _set_claims(oidc_context, parameters, sub="mfa-subject")
    callback = _callback(oidc_context, parameters)
    assert callback.status_code == 200
    challenge = callback.json()
    assert challenge["mfa_required"] is True
    assert "access_token" not in challenge

    verified = oidc_context.client.post(
        "/auth/mfa/challenge/verify",
        json={
            "challenge_token": challenge["challenge_token"],
            "code": pyotp.TOTP(secret).now(),
        },
    )
    assert verified.status_code == 200
    assert set(decode_token(verified.json()["access_token"]).amr) == {"oidc", "otp"}
    assert require_recent_mfa(verified.json()["access_token"]).sub == local.username


def test_oidc_provider_validates_discovery_signature_audience_and_azp(monkeypatch):
    issuer = "https://provider.example"
    monkeypatch.setattr(settings, "OIDC_ISSUER", issuer)
    monkeypatch.setattr(settings, "OIDC_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "OIDC_ALLOWED_ALGORITHMS", "RS256")
    client = OIDCProviderClient()
    discovery = {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "jwks_uri": f"{issuer}/jwks",
        "code_challenge_methods_supported": ["S256"],
    }
    monkeypatch.setattr(
        client, "_request_json", lambda method, url, **kwargs: discovery
    )
    metadata = client.discover()

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": "key-1", "alg": "RS256", "use": "sig"})
    monkeypatch.setattr(
        client,
        "_request_json",
        lambda method, url, **kwargs: {"keys": [jwk]},
    )
    now = datetime.now(UTC)
    claims = {
        "iss": issuer,
        "sub": "subject",
        "aud": ["client-id", "another-audience"],
        "azp": "client-id",
        "nonce": "nonce",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    encoded = jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "key-1"},
    )
    assert client.validate_id_token(metadata, encoded)["sub"] == "subject"

    claims["azp"] = "wrong-client"
    wrong_azp = jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "key-1"},
    )
    with pytest.raises(OIDCProviderError):
        client.validate_id_token(metadata, wrong_azp)

    claims["aud"] = "wrong-audience"
    claims["azp"] = None
    wrong_audience = jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "key-1"},
    )
    with pytest.raises(OIDCProviderError):
        client.validate_id_token(metadata, wrong_audience)

    unsigned_algorithm = jwt.encode(
        {**claims, "aud": "client-id"},
        "symmetric-test-secret-that-is-at-least-32-bytes",
        algorithm="HS256",
        headers={"kid": "key-1"},
    )
    with pytest.raises(OIDCProviderError):
        client.validate_id_token(metadata, unsigned_algorithm)


def test_oidc_discovery_rejects_issuer_mismatch_and_missing_s256(monkeypatch):
    issuer = "https://provider.example"
    monkeypatch.setattr(settings, "OIDC_ISSUER", issuer)
    client = OIDCProviderClient()
    payload = {
        "issuer": "https://other-provider.example",
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "jwks_uri": f"{issuer}/jwks",
        "code_challenge_methods_supported": ["S256"],
    }
    monkeypatch.setattr(client, "_request_json", lambda method, url, **kwargs: payload)
    with pytest.raises(OIDCProviderError, match="issuer mismatch"):
        client.discover()

    payload["issuer"] = issuer
    payload["code_challenge_methods_supported"] = ["plain"]
    with pytest.raises(OIDCProviderError, match="PKCE S256"):
        client.discover()


def test_oidc_provider_exchanges_code_without_following_redirects(monkeypatch):
    issuer = "https://provider.example"
    monkeypatch.setattr(settings, "OIDC_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "OIDC_CLIENT_SECRET", SecretStr("client-secret"))
    observed: dict = {}

    def handler(request: httpx.Request):
        observed["method"] = request.method
        observed["authorization"] = request.headers.get("authorization")
        observed["body"] = request.content.decode()
        return httpx.Response(200, json={"id_token": "signed-token"})

    client = OIDCProviderClient(transport=httpx.MockTransport(handler))
    metadata = OIDCMetadata(
        issuer=issuer,
        authorization_endpoint=f"{issuer}/authorize",
        token_endpoint=f"{issuer}/token",
        jwks_uri=f"{issuer}/jwks",
    )
    token = client.exchange_code(
        metadata,
        code="authorization-code",
        code_verifier="v" * 43,
        redirect_uri="https://client.example/callback",
    )
    assert token == "signed-token"
    assert observed["method"] == "POST"
    assert observed["authorization"].startswith("Basic ")
    assert "code_verifier=" in observed["body"]
    assert "client_secret" not in observed["body"]


def test_oidc_provider_controls_http_and_token_response_failures(monkeypatch):
    issuer = "https://provider.example"
    metadata = OIDCMetadata(
        issuer=issuer,
        authorization_endpoint=f"{issuer}/authorize",
        token_endpoint=f"{issuer}/token",
        jwks_uri=f"{issuer}/jwks",
    )
    monkeypatch.setattr(settings, "OIDC_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "OIDC_CLIENT_SECRET", SecretStr("client-secret"))
    monkeypatch.setattr(
        settings, "OIDC_TOKEN_ENDPOINT_AUTH_METHOD", "client_secret_post"
    )

    def missing_token(request: httpx.Request):
        assert "client_secret=client-secret" in request.content.decode()
        return httpx.Response(200, json={"access_token": "not-an-id-token"})

    client = OIDCProviderClient(transport=httpx.MockTransport(missing_token))
    with pytest.raises(OIDCProviderError, match="did not contain an ID token"):
        client.exchange_code(
            metadata,
            code="code",
            code_verifier="v" * 43,
            redirect_uri="https://client.example/callback",
        )

    failing = OIDCProviderClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500, json={"error": "server_error"})
        )
    )
    with pytest.raises(OIDCProviderError, match="provider request failed"):
        failing.exchange_code(
            metadata,
            code="code",
            code_verifier="v" * 43,
            redirect_uri="https://client.example/callback",
        )
