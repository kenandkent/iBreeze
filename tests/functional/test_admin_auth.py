"""Test admin authentication flow - login, refresh, logout."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_refresh_logout_flow(
    app_client: AsyncClient, admin_credentials: dict
):
    # Login
    login_resp = await app_client.post(
        "/admin/api/v1/auth/login",
        json={
            "identifier": admin_credentials["identifier"],
            "password": admin_credentials["password"],
            "device_id": "00000000-0000-0000-0000-000000000001",
        },
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "data" in data
    assert "access_token" in data["data"]
    assert "user" in data["data"]

    # Refresh
    cookies = login_resp.cookies
    refresh_resp = await app_client.post("/admin/api/v1/auth/refresh", cookies=cookies)
    assert refresh_resp.status_code == 200
    refresh_data = refresh_resp.json()
    assert "data" in refresh_data
    assert "access_token" in refresh_data["data"]

    # Logout
    token = data["data"]["access_token"]
    logout_resp = await app_client.post(
        "/admin/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_resp.status_code == 204
