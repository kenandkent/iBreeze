"""Compatibility layer API endpoint tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


def _auth(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _rule_body() -> dict[str, object]:
    return {
        "subject_type": "agent",
        "subject_id": str(uuid.uuid4()),
        "subject_version_range": ">=1.0.0 <2.0.0",
        "dependency_type": "model",
        "dependency_key": "openai/gpt-5",
        "dependency_version_range": "^1.0.0",
        "decision": "allow",
        "reason_code": "api_test",
        "priority": 100,
    }


@pytest.mark.asyncio
class TestCompatibilityEndpoints:
    async def test_list_rules(self, client: AsyncClient, admin_tokens):
        resp = await client.get(
            "/admin/api/v1/compatibility-rules",
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "next_cursor" in body

    async def test_create_rule(self, client: AsyncClient, admin_tokens):
        resp = await client.post(
            "/admin/api/v1/compatibility-rules",
            json=_rule_body(),
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 201
        assert resp.json()["decision"] == "allow"

    async def test_get_rule(self, client: AsyncClient, admin_tokens):
        created = await client.post(
            "/admin/api/v1/compatibility-rules",
            json=_rule_body(),
            headers=_auth(admin_tokens),
        )
        rule_id = created.json()["id"]
        resp = await client.get(
            f"/admin/api/v1/compatibility-rules/{rule_id}",
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == rule_id

    async def test_validate_rule(self, client: AsyncClient, admin_tokens):
        created = await client.post(
            "/admin/api/v1/compatibility-rules",
            json=_rule_body(),
            headers=_auth(admin_tokens),
        )
        resp = await client.post(
            f"/admin/api/v1/compatibility-rules/{created.json()['id']}/validate",
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "validated"

    async def test_list_rules_require_auth(self, client: AsyncClient):
        resp = await client.get("/admin/api/v1/compatibility-rules")
        assert resp.status_code in (401, 403)

    async def test_create_rule_require_auth(self, client: AsyncClient):
        resp = await client.post(
            "/admin/api/v1/compatibility-rules",
            json=_rule_body(),
        )
        assert resp.status_code in (401, 403)

    async def test_update_rule_decision(self, client: AsyncClient, admin_tokens):
        created = await client.post(
            "/admin/api/v1/compatibility-rules",
            json=_rule_body(),
            headers=_auth(admin_tokens),
        )
        rule_id = created.json()["id"]
        version = created.json()["version"]
        resp = await client.patch(
            f"/admin/api/v1/compatibility-rules/{rule_id}",
            json={"decision": "deny"},
            headers={**_auth(admin_tokens), "If-Match": str(version)},
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "deny"

    async def test_update_requires_if_match(self, client: AsyncClient, admin_tokens):
        created = await client.post(
            "/admin/api/v1/compatibility-rules",
            json=_rule_body(),
            headers=_auth(admin_tokens),
        )
        resp = await client.patch(
            f"/admin/api/v1/compatibility-rules/{created.json()['id']}",
            json={"decision": "deny"},
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 428

    async def test_public_list_published_rules(self, client: AsyncClient):
        resp = await client.get("/api/v1/catalog/compatibility")
        assert resp.status_code == 200
        assert "data" in resp.json()
        assert "meta" in resp.json()
