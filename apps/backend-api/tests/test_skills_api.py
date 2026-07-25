"""Skills API endpoint tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


def _auth(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.mark.asyncio
class TestSkillsEndpoints:
    async def test_list_skills(self, client: AsyncClient, admin_tokens):
        resp = await client.get(
            "/admin/api/v1/skills",
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "next_cursor" in body

    async def test_list_skills_require_auth(self, client: AsyncClient):
        resp = await client.get("/admin/api/v1/skills")
        assert resp.status_code in (401, 403)

    async def test_create_skill(self, client: AsyncClient, admin_tokens):
        resp = await client.post(
            "/admin/api/v1/skills",
            json={
                "key": "test-skill-api",
                "display_name": "Test Skill",
                "description": "A test skill.",
            },
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 201
        assert resp.json()["key"] == "test-skill-api"

    async def test_get_skill(self, client: AsyncClient, admin_tokens):
        created = await client.post(
            "/admin/api/v1/skills",
            json={
                "key": "get-skill-api",
                "display_name": "Get Skill",
                "description": "Get test.",
            },
            headers=_auth(admin_tokens),
        )
        skill_id = created.json()["id"]
        resp = await client.get(
            f"/admin/api/v1/skills/{skill_id}",
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == skill_id

    async def test_get_skill_not_found(self, client: AsyncClient, admin_tokens):
        resp = await client.get(
            "/admin/api/v1/skills/00000000-0000-0000-0000-000000000000",
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 404

    async def test_upload_skill_requires_zip(self, client: AsyncClient, admin_tokens):
        created = await client.post(
            "/admin/api/v1/skills",
            json={
                "key": "upload-skill-api",
                "display_name": "Upload Skill",
                "description": "Upload test.",
            },
            headers=_auth(admin_tokens),
        )
        skill_id = created.json()["id"]
        resp = await client.post(
            f"/admin/api/v1/skills/{skill_id}/versions",
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 422

    async def test_app_user_cannot_manage_skills(self, client: AsyncClient, user_tokens):
        resp = await client.get(
            "/admin/api/v1/skills",
            headers=_auth(user_tokens),
        )
        assert resp.status_code in (401, 403)

    async def test_list_skill_versions(self, client: AsyncClient, admin_tokens):
        created = await client.post(
            "/admin/api/v1/skills",
            json={
                "key": "versions-skill-api",
                "display_name": "Versions Skill",
                "description": "Versions test.",
            },
            headers=_auth(admin_tokens),
        )
        skill_id = created.json()["id"]
        resp = await client.get(
            f"/admin/api/v1/skills/{skill_id}/versions",
            headers=_auth(admin_tokens),
        )
        assert resp.status_code == 200
        assert "items" in resp.json()
