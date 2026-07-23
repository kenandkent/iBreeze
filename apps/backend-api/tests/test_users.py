"""User management tests."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_app_user(client: AsyncClient, admin_tokens):
    """Test creating an app user."""
    response = await client.post(
        "/admin/api/v1/users",
        json={
            "email": "newappuser@example.com",
            "password": "password123",
            "user_type": "app_user",
        },
        headers={
            "Authorization": f"Bearer {admin_tokens['access_token']}",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["user_type"] == "app_user"


@pytest.mark.asyncio
async def test_create_admin_user(client: AsyncClient, admin_tokens):
    """Test creating an admin user."""
    response = await client.post(
        "/admin/api/v1/users",
        json={
            "email": "newadmin@example.com",
            "password": "password123",
            "user_type": "admin",
        },
        headers={
            "Authorization": f"Bearer {admin_tokens['access_token']}",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["user_type"] == "admin"


@pytest.mark.asyncio
async def test_protected_admin_cannot_delete(client: AsyncClient, admin_tokens, test_admin):
    """Test protected admin cannot be deleted."""
    response = await client.delete(
        f"/admin/api/v1/users/{test_admin.id}",
        headers={
            "Authorization": f"Bearer {admin_tokens['access_token']}",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_protected_admin_cannot_disable(client: AsyncClient, admin_tokens, test_admin):
    """Test protected admin cannot be disabled."""
    response = await client.patch(
        f"/admin/api/v1/users/{test_admin.id}",
        json={"is_active": False},
        headers={
            "Authorization": f"Bearer {admin_tokens['access_token']}",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_protected_admin_cannot_rename(client: AsyncClient, admin_tokens, test_admin):
    """Test protected admin cannot be renamed."""
    response = await client.patch(
        f"/admin/api/v1/users/{test_admin.id}",
        json={"email": "new@example.com"},
        headers={
            "Authorization": f"Bearer {admin_tokens['access_token']}",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_delete_regular_user(client: AsyncClient, admin_tokens, test_user):
    """Test deleting a regular user."""
    response = await client.delete(
        f"/admin/api/v1/users/{test_user.id}",
        headers={
            "Authorization": f"Bearer {admin_tokens['access_token']}",
        },
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_reset_password(client: AsyncClient, admin_tokens, test_user):
    """Test resetting user password."""
    response = await client.post(
        f"/admin/api/v1/users/{test_user.id}/reset-password",
        json={"new_password": "NewPass1234"},
        headers={
            "Authorization": f"Bearer {admin_tokens['access_token']}",
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_revoke_sessions(client: AsyncClient, admin_tokens, test_user):
    """Test revoking user sessions."""
    response = await client.post(
        f"/admin/api/v1/users/{test_user.id}/revoke-sessions",
        headers={
            "Authorization": f"Bearer {admin_tokens['access_token']}",
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_users(client: AsyncClient, admin_tokens):
    """Test listing users."""
    response = await client.get(
        "/admin/api/v1/users",
        headers={
            "Authorization": f"Bearer {admin_tokens['access_token']}",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "users" in data


@pytest.mark.asyncio
async def test_list_users_with_pagination(client: AsyncClient, admin_tokens):
    """Test listing users with pagination."""
    response = await client.get(
        "/admin/api/v1/users?limit=10",
        headers={
            "Authorization": f"Bearer {admin_tokens['access_token']}",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "users" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_invalid_limit(client: AsyncClient, admin_tokens):
    """Test invalid limit value is rejected."""
    response = await client.get(
        "/admin/api/v1/users?limit=0",
        headers={
            "Authorization": f"Bearer {admin_tokens['access_token']}",
        },
    )
    assert response.status_code == 422

    response = await client.get(
        "/admin/api/v1/users?limit=300",
        headers={
            "Authorization": f"Bearer {admin_tokens['access_token']}",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_user_email(client: AsyncClient, admin_tokens, test_user):
    """Test updating user email."""
    response = await client.patch(
        f"/admin/api/v1/users/{test_user.id}",
        json={"email": "updated@example.com"},
        headers={
            "Authorization": f"Bearer {admin_tokens['access_token']}",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "updated@example.com"
