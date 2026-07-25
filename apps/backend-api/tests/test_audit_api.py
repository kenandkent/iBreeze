"""Audit log API endpoint tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


def _auth(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.mark.asyncio
class TestAuditEndpoints:
    async def test_list_audit_logs(self, client: AsyncClient, admin_tokens):
        resp = await client.get(
            "/admin/api/v1/audit-logs",
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert body["meta"]["limit"] == 50

    async def test_audit_logs_require_auth(self, client: AsyncClient):
        resp = await client.get("/admin/api/v1/audit-logs")
        assert resp.status_code in (401, 403)

    async def test_audit_logs_filter_by_action(self, client: AsyncClient, admin_tokens):
        resp = await client.get(
            "/admin/api/v1/audit-logs",
            params={"action": "user.create"},
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 200
        assert "data" in resp.json()

    async def test_audit_logs_filter_by_actor(self, client: AsyncClient, admin_tokens):
        resp = await client.get(
            "/admin/api/v1/audit-logs",
            params={"actor_id": "00000000-0000-0000-0000-000000000001"},
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 200

    async def test_audit_logs_filter_by_resource_type(self, client: AsyncClient, admin_tokens):
        resp = await client.get(
            "/admin/api/v1/audit-logs",
            params={"resource_type": "admin"},
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 200

    async def test_audit_logs_limit_range(self, client: AsyncClient, admin_tokens):
        resp = await client.get(
            "/admin/api/v1/audit-logs",
            params={"limit": 200},
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["limit"] == 200

    async def test_audit_logs_limit_over_max_rejected(self, client: AsyncClient, admin_tokens):
        resp = await client.get(
            "/admin/api/v1/audit-logs",
            params={"limit": 201},
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 422

    async def test_audit_logs_offset(self, client: AsyncClient, admin_tokens):
        resp = await client.get(
            "/admin/api/v1/audit-logs",
            params={"offset": 10},
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["offset"] == 10

    async def test_audit_logs_offset_negative_rejected(self, client: AsyncClient, admin_tokens):
        resp = await client.get(
            "/admin/api/v1/audit-logs",
            params={"offset": -1},
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 422

    async def test_audit_log_entry_shape(self, client: AsyncClient, admin_tokens):
        resp = await client.get(
            "/admin/api/v1/audit-logs",
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 200
        for entry in resp.json()["data"]:
            assert "id" in entry
            assert "action" in entry
            assert "created_at" in entry

    async def test_app_user_cannot_access_audit_logs(self, client: AsyncClient, user_tokens):
        resp = await client.get(
            "/admin/api/v1/audit-logs",
            headers=_auth(user_tokens),
        )
        assert resp.status_code in (401, 403)
