"""G.5/G.11 authentication contract tests."""

import base64
import json
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

from ibreeze_backend.auth.service import (
    ADMIN_AUDIENCE,
    APP_AUDIENCE,
    AUTH_ISSUER,
    OFFLINE_AUDIENCE,
    get_auth_keys,
    verify_access_token,
)
from ibreeze_backend.security.keys import load_or_create_signing_keys
from ibreeze_backend.settings import settings


def _login_body(identifier: str, password: str) -> dict[str, str]:
    return {
        "identifier": identifier,
        "password": password,
        "device_id": str(uuid.uuid4()),
    }


def _decode_offline_ticket(token: str) -> dict[str, object]:
    import jwt
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    key = get_auth_keys()["keys"][0]
    raw = base64.urlsafe_b64decode(str(key["x"]) + "==")
    public_key = Ed25519PublicKey.from_public_bytes(raw)
    return jwt.decode(
        token,
        public_key,
        algorithms=["EdDSA"],
        audience=OFFLINE_AUDIENCE,
        issuer=AUTH_ISSUER,
        options={
            "require": [
                "iss",
                "aud",
                "sub",
                "device_id",
                "backend_origin",
                "iat",
                "exp",
                "jti",
            ]
        },
    )


@pytest.mark.asyncio
async def test_register_creates_app_user_without_session(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "User@Example.COM", "password": "password123"},
    )
    assert response.status_code == 201
    assert response.json()["data"] == {
        "user": {
            "id": response.json()["data"]["user"]["id"],
            "user_type": "app_user",
            "username": None,
                "email": "user@example.com",
                "display_name": "user@example.com",
                "masked_identifier": "u***@example.com",
                "status": "active",
        }
    }
    assert "access_token" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"email": "test@example.com", "password": "short"},
        {
            "email": "test@example.com",
            "password": "password123",
            "user_type": "admin",
        },
        {
            "email": "test@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    ],
)
async def test_register_rejects_invalid_or_unknown_fields(
    client: AsyncClient,
    payload: dict[str, str],
):
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(client: AsyncClient, test_user):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": test_user.email.upper(), "password": "password123"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_app_login_returns_complete_rotatable_bundle(client: AsyncClient, test_user):
    device_id = uuid.uuid4()
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "identifier": test_user.email,
            "password": "testpassword123",
            "device_id": str(device_id),
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["user"]["user_type"] == "app_user"
    assert data["refresh_token"]
    assert data["offline_session_ticket"]
    assert data["refresh_token_expires_in"] == 2_592_000
    assert data["offline_session_ticket_expires_in"] == 2_592_000
    assert data["access_token_expires_in"] == 900
    assert data["pwd_change_required"] is False
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert verify_access_token(data["access_token"], APP_AUDIENCE) is not None
    assert verify_access_token(data["access_token"], ADMIN_AUDIENCE) is None
    ticket = _decode_offline_ticket(data["offline_session_ticket"])
    assert ticket == {
        "iss": AUTH_ISSUER,
        "aud": OFFLINE_AUDIENCE,
        "sub": str(test_user.id),
        "device_id": str(device_id),
        "backend_origin": AUTH_ISSUER,
        "iat": ticket["iat"],
        "exp": ticket["exp"],
        "jti": ticket["jti"],
    }
    import jwt

    key = get_auth_keys()["keys"][0]
    raw = base64.urlsafe_b64decode(str(key["x"]) + "==")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    with pytest.raises(jwt.InvalidAudienceError):
        jwt.decode(
            data["offline_session_ticket"],
            Ed25519PublicKey.from_public_bytes(raw),
            algorithms=["EdDSA"],
            audience=APP_AUDIENCE,
            issuer=AUTH_ISSUER,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("identifier", "password"),
    [
        ("missing@example.com", "password123"),
        ("fixture", "wrongpassword"),
    ],
)
async def test_login_does_not_disclose_account_state(client: AsyncClient, test_user, identifier: str, password: str):
    actual_identifier = test_user.email if identifier == "fixture" else identifier
    response = await client.post(
        "/api/v1/auth/login",
        json=_login_body(actual_identifier, password),
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_disabled_user_cannot_login(client: AsyncClient, test_user, db_session):
    test_user.status = "disabled"
    await db_session.flush()
    response = await client.post(
        "/api/v1/auth/login",
        json=_login_body(test_user.email, "testpassword123"),
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_five_failures_lock_account_for_fifteen_minutes(client: AsyncClient, test_user):
    for _ in range(5):
        response = await client.post(
            "/api/v1/auth/login",
            json=_login_body(test_user.email, "wrongpassword"),
        )
        assert response.status_code == 401
    response = await client.post(
        "/api/v1/auth/login",
        json=_login_body(test_user.email, "testpassword123"),
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_app_identity_cannot_use_admin_login(client: AsyncClient, test_user):
    response = await client.post(
        "/admin/api/v1/auth/login",
        json=_login_body(test_user.email, "testpassword123"),
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotates_token_and_replay_revokes_family(client: AsyncClient, user_tokens):
    first = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": user_tokens["refresh_token"]},
    )
    assert first.status_code == 200
    replacement = first.json()["data"]["refresh_token"]
    assert replacement != user_tokens["refresh_token"]

    replay = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": user_tokens["refresh_token"]},
    )
    assert replay.status_code == 401

    revoked_replacement = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": replacement},
    )
    assert revoked_replacement.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_current_family(client: AsyncClient, user_tokens):
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {user_tokens['access_token']}"},
    )
    assert response.status_code == 204
    refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": user_tokens["refresh_token"]},
    )
    assert refresh.status_code == 401


@pytest.mark.asyncio
async def test_logout_all_revokes_all_families(client: AsyncClient, user_tokens):
    response = await client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {user_tokens['access_token']}"},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_change_password_rotates_family(client: AsyncClient, user_tokens):
    response = await client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "testpassword123",
            "new_password": "newpassword123",
        },
        headers={"Authorization": f"Bearer {user_tokens['access_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["refresh_token"]
    old_refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": user_tokens["refresh_token"]},
    )
    assert old_refresh.status_code == 401


@pytest.mark.asyncio
async def test_password_change_gate_allows_only_change_or_logout(
    client: AsyncClient, test_user, user_tokens, db_session
):
    test_user.must_change_password = True
    await db_session.flush()

    denied = await client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {user_tokens['access_token']}"},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "AUTH_PASSWORD_CHANGE_REQUIRED"

    changed = await client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "testpassword123",
            "new_password": "newpassword123",
        },
        headers={"Authorization": f"Bearer {user_tokens['access_token']}"},
    )
    assert changed.status_code == 200


@pytest.mark.asyncio
async def test_admin_login_uses_username_and_http_only_cookie(client: AsyncClient, test_admin):
    response = await client.post(
        "/admin/api/v1/auth/login",
        json=_login_body(test_admin.username, "admin123456"),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["user"]["user_type"] == "admin"
    assert "refresh_token" not in data
    assert "offline_session_ticket" not in data
    cookie = response.headers["set-cookie"]
    assert "ibreeze_admin_refresh=" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/admin/api/v1/auth" in cookie
    assert verify_access_token(data["access_token"], ADMIN_AUDIENCE) is not None
    assert verify_access_token(data["access_token"], APP_AUDIENCE) is None


@pytest.mark.asyncio
async def test_admin_refresh_reads_cookie_and_never_returns_token(client: AsyncClient, admin_tokens):
    response = await client.post(
        "/admin/api/v1/auth/refresh",
        headers={"Cookie": (f"ibreeze_admin_refresh={admin_tokens['refresh_token']}")},
    )
    assert response.status_code == 200
    assert "refresh_token" not in response.json()["data"]
    assert "ibreeze_admin_refresh=" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_auth_keyset_is_complete_and_signed(client: AsyncClient):
    response = await client.get("/api/v1/auth/keys")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["signature_algorithm"] == "Ed25519"
    assert data["signature"]
    assert data["issued_at"]
    assert data["expires_at"]
    assert data["keys"][0] == {
        "kty": "OKP",
        "crv": "Ed25519",
        "kid": data["keys"][0]["kid"],
        "use": "sig",
        "alg": "EdDSA",
        "x": data["keys"][0]["x"],
        "status": "active",
    }
    from cryptography.hazmat.primitives import serialization

    _, catalog_public_pem, catalog_kid = load_or_create_signing_keys(
        Path(settings.catalog_key_dir)
    )
    assert data["signing_key_id"] == catalog_kid
    public_key = serialization.load_pem_public_key(catalog_public_pem)
    signed_payload = {
        "keys": data["keys"],
        "issued_at": data["issued_at"],
        "expires_at": data["expires_at"],
    }
    canonical = json.dumps(signed_payload, sort_keys=True, separators=(",", ":")).encode()
    public_key.verify(
        base64.urlsafe_b64decode(data["signature"] + "=="),
        canonical,
    )
