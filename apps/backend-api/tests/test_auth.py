"""Authentication tests."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    """Test successful user registration."""
    response = await client.post(
        "/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_email_normalization(client: AsyncClient):
    """Test email is normalized to lowercase."""
    response = await client.post(
        "/auth/register",
        json={
            "email": "User@Example.COM",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_register_password_too_short(client: AsyncClient):
    """Test registration with too short password."""
    response = await client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "password": "short",
            "confirm_password": "short",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_password_too_long(client: AsyncClient):
    """Test registration with too long password."""
    response = await client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "password": "a" * 129,
            "confirm_password": "a" * 129,
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_password_mismatch(client: AsyncClient):
    """Test registration with mismatched passwords."""
    response = await client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "password": "password123",
            "confirm_password": "password456",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, test_user):
    """Test registration with duplicate email."""
    response = await client.post(
        "/auth/register",
        json={
            "email": test_user.email,
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_register_ignores_user_type(client: AsyncClient):
    """Test that registration ignores user_type field."""
    response = await client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "password": "password123",
            "confirm_password": "password123",
            "user_type": "admin",
        },
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user):
    """Test successful login."""
    response = await client.post(
        "/auth/login",
        json={
            "email": test_user.email,
            "password": "testpassword123",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user_type"] == "app_user"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user):
    """Test login with wrong password."""
    response = await client.post(
        "/auth/login",
        json={
            "email": test_user.email,
            "password": "wrongpassword",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    """Test login with nonexistent user (should not reveal user doesn't exist)."""
    response = await client.post(
        "/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_login_disabled_user(client: AsyncClient, test_user, db_session):
    """Test login with disabled user."""
    from ibreeze_backend.models.user import User

    test_user.is_active = False
    await db_session.commit()

    response = await client.post(
        "/auth/login",
        json={
            "email": test_user.email,
            "password": "testpassword123",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_login_wrong_audience(client: AsyncClient, test_user):
    """Test login with wrong audience."""
    response = await client.post(
        "/admin/api/v1/auth/login",
        json={
            "email": test_user.email,
            "password": "testpassword123",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_rotation(client: AsyncClient, user_tokens):
    """Test refresh token rotation."""
    response = await client.post(
        "/auth/refresh",
        json={
            "refresh_token": user_tokens["refresh_token"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "token_type" in data


@pytest.mark.asyncio
async def test_refresh_token_replay_detection(client: AsyncClient, user_tokens):
    """Test refresh token replay detection."""
    # First refresh should succeed
    response1 = await client.post(
        "/auth/refresh",
        json={
            "refresh_token": user_tokens["refresh_token"],
        },
    )
    assert response1.status_code == 200

    # Second refresh with same token should fail (replay detected)
    response2 = await client.post(
        "/auth/refresh",
        json={
            "refresh_token": user_tokens["refresh_token"],
        },
    )
    assert response2.status_code == 401


@pytest.mark.asyncio
async def test_logout(client: AsyncClient, user_tokens):
    """Test logout."""
    response = await client.post(
        "/auth/logout",
        headers={
            "Authorization": f"Bearer {user_tokens['access_token']}",
        },
    )
    assert response.status_code == 204

    # Refresh should fail after logout
    response = await client.post(
        "/auth/refresh",
        json={
            "refresh_token": user_tokens["refresh_token"],
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_all(client: AsyncClient, user_tokens):
    """Test logout all devices."""
    response = await client.post(
        "/auth/logout-all",
        headers={
            "Authorization": f"Bearer {user_tokens['access_token']}",
        },
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_change_password(client: AsyncClient, user_tokens):
    """Test password change."""
    response = await client.post(
        "/auth/change-password",
        json={
            "old_password": "testpassword123",
            "new_password": "newpassword123",
            "confirm_password": "newpassword123",
        },
        headers={
            "Authorization": f"Bearer {user_tokens['access_token']}",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_change_password_wrong_old_password(client: AsyncClient, user_tokens):
    """Test password change with wrong old password."""
    response = await client.post(
        "/auth/change-password",
        json={
            "old_password": "wrongpassword",
            "new_password": "newpassword123",
            "confirm_password": "newpassword123",
        },
        headers={
            "Authorization": f"Bearer {user_tokens['access_token']}",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_admin_login(client: AsyncClient, test_admin):
    """Test admin login."""
    response = await client.post(
        "/admin/api/v1/auth/login",
        json={
            "email": test_admin.email,
            "password": "admin123456",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user_type"] == "admin"


@pytest.mark.asyncio
async def test_admin_refresh(client: AsyncClient, admin_tokens):
    """Test admin token refresh."""
    response = await client.post(
        "/admin/api/v1/auth/refresh",
        json={
            "refresh_token": admin_tokens["refresh_token"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_admin_logout(client: AsyncClient, admin_tokens):
    """Test admin logout."""
    response = await client.post(
        "/admin/api/v1/auth/logout",
        headers={
            "Authorization": f"Bearer {admin_tokens['access_token']}",
        },
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_get_auth_keys(client: AsyncClient, user_tokens):
    """Test get auth keys endpoint."""
    response = await client.get(
        "/auth/keys",
        headers={
            "Authorization": f"Bearer {user_tokens['access_token']}",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "keys" in data
    assert len(data["keys"]) > 0
    assert data["keys"][0]["kty"] == "OKP"
    assert data["keys"][0]["crv"] == "Ed25519"
