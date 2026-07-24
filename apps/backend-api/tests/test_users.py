"""Admin user management contract tests."""

import pytest
from httpx import AsyncClient


def _auth(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.mark.asyncio
async def test_create_app_user(client: AsyncClient, admin_tokens):
    response = await client.post(
        "/admin/api/v1/users",
        json={
            "user_type": "app_user",
            "email": " NewAppUser@Example.com ",
            "display_name": "New App User",
            "password": "password123",
        },
        headers=_auth(admin_tokens),
    )

    assert response.status_code == 201, response.text
    assert response.json() == {
        **response.json(),
        "user_type": "app_user",
        "username": None,
        "email": "newappuser@example.com",
        "display_name": "New App User",
        "status": "active",
    }


@pytest.mark.asyncio
async def test_create_admin_user(client: AsyncClient, admin_tokens):
    response = await client.post(
        "/admin/api/v1/users",
        json={
            "user_type": "admin",
            "username": "release-admin",
            "display_name": "Release Admin",
            "password": "password123",
        },
        headers=_auth(admin_tokens),
    )

    assert response.status_code == 201, response.text
    assert response.json()["user_type"] == "admin"
    assert response.json()["username"] == "release-admin"
    assert response.json()["email"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {
            "user_type": "admin",
            "username": "admin-with-email",
            "email": "forbidden@example.com",
            "display_name": "Invalid",
            "password": "password123",
        },
        {
            "user_type": "app_user",
            "username": "forbidden",
            "email": "valid@example.com",
            "display_name": "Invalid",
            "password": "password123",
        },
        {
            "user_type": "admin",
            "display_name": "Missing Username",
            "password": "password123",
        },
    ],
)
async def test_create_user_enforces_identity_field_union(client: AsyncClient, admin_tokens, payload):
    response = await client.post(
        "/admin/api/v1/users",
        json=payload,
        headers=_auth(admin_tokens),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_protected_admin_allows_only_display_name(client: AsyncClient, admin_tokens, test_admin):
    display_response = await client.patch(
        f"/admin/api/v1/users/{test_admin.id}",
        json={"display_name": "Platform Owner"},
        headers=_auth(admin_tokens),
    )
    username_response = await client.patch(
        f"/admin/api/v1/users/{test_admin.id}",
        json={"username": "renamed-admin"},
        headers=_auth(admin_tokens),
    )
    status_response = await client.patch(
        f"/admin/api/v1/users/{test_admin.id}",
        json={"status": "disabled"},
        headers=_auth(admin_tokens),
    )

    assert display_response.status_code == 200
    assert display_response.json()["display_name"] == "Platform Owner"
    assert username_response.status_code == 400
    assert status_response.status_code == 400


@pytest.mark.asyncio
async def test_protected_admin_cannot_delete(client: AsyncClient, admin_tokens, test_admin):
    response = await client.delete(
        f"/admin/api/v1/users/{test_admin.id}",
        headers=_auth(admin_tokens),
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_delete_regular_user(client: AsyncClient, admin_tokens, test_user):
    response = await client.delete(
        f"/admin/api/v1/users/{test_user.id}",
        headers=_auth(admin_tokens),
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_reset_password_sets_change_gate(client: AsyncClient, admin_tokens, test_user):
    response = await client.post(
        f"/admin/api/v1/users/{test_user.id}/reset-password",
        json={"new_password": "NewPass1234"},
        headers=_auth(admin_tokens),
    )

    assert response.status_code == 200
    assert response.json()["must_change_password"] is True


@pytest.mark.asyncio
async def test_revoke_sessions(client: AsyncClient, admin_tokens, test_user):
    response = await client.post(
        f"/admin/api/v1/users/{test_user.id}/revoke-sessions",
        headers=_auth(admin_tokens),
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_users_with_cursor_metadata(client: AsyncClient, admin_tokens):
    response = await client.get(
        "/admin/api/v1/users?limit=10",
        headers=_auth(admin_tokens),
    )

    assert response.status_code == 200
    assert "users" in response.json()
    assert "next_cursor" in response.json()
    assert "total" in response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 201])
async def test_invalid_limit(client: AsyncClient, admin_tokens, limit: int):
    response = await client.get(
        f"/admin/api/v1/users?limit={limit}",
        headers=_auth(admin_tokens),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_app_user_fields(client: AsyncClient, admin_tokens, test_user):
    response = await client.patch(
        f"/admin/api/v1/users/{test_user.id}",
        json={
            "email": " Updated@Example.com ",
            "display_name": "Updated User",
            "status": "disabled",
        },
        headers=_auth(admin_tokens),
    )

    assert response.status_code == 200, response.text
    assert response.json()["email"] == "updated@example.com"
    assert response.json()["display_name"] == "Updated User"
    assert response.json()["status"] == "disabled"


@pytest.mark.asyncio
async def test_user_patch_rejects_unknown_field(client: AsyncClient, admin_tokens, test_user):
    response = await client.patch(
        f"/admin/api/v1/users/{test_user.id}",
        json={"role": "viewer"},
        headers=_auth(admin_tokens),
    )
    assert response.status_code == 422
