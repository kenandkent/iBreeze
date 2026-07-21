import pytest
from httpx import AsyncClient

from app.auth.jwt import create_access_token
from app.models.admin import AdminUser
from app.models.capability import Skill


@pytest.fixture
async def auth_header(db_session):
    user = AdminUser(
        user_id="user-1",
        username="testadmin",
        password_hash="x",
        role="super_admin",
        status="active",
    )
    db_session.add(user)
    await db_session.commit()
    token = create_access_token("user-1", "super_admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def seed_skill(db_session):
    skill = Skill(
        skill_id="skill-1",
        company_id="comp-1",
        name="Test Skill",
        description="A test skill",
        prompt_asset_id="prompt-1",
        status="draft",
        version=1,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    db_session.add(skill)
    await db_session.commit()


class TestSkillsAPI:
    async def test_list_skills_empty(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/skills", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_skill(self, client: AsyncClient, auth_header):
        resp = await client.post(
            "/api/skills",
            json={"company_id": "comp-1", "name": "New Skill"},
            headers=auth_header,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "New Skill"
        assert data["status"] == "draft"
        assert data["version"] == 1

    async def test_get_skill(self, client: AsyncClient, auth_header, seed_skill):
        resp = await client.get("/api/skills/skill-1", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test Skill"

    async def test_get_skill_not_found(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/skills/nonexistent", headers=auth_header)
        assert resp.status_code == 404

    async def test_update_skill(self, client: AsyncClient, auth_header, seed_skill):
        resp = await client.put(
            "/api/skills/skill-1",
            json={"name": "Updated Skill"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Skill"
        assert data["version"] == 2

    async def test_update_skill_not_found(self, client: AsyncClient, auth_header):
        resp = await client.put(
            "/api/skills/nonexistent",
            json={"name": "X"},
            headers=auth_header,
        )
        assert resp.status_code == 404

    async def test_state_transitions(self, client: AsyncClient, auth_header, seed_skill):
        # draft -> review
        resp = await client.post("/api/skills/skill-1/submit-review", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "review"

        # review -> published
        resp = await client.post("/api/skills/skill-1/publish", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "published"

        # published -> deprecated
        resp = await client.post("/api/skills/skill-1/deprecate", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "deprecated"

        # deprecated -> archived
        resp = await client.post("/api/skills/skill-1/archive", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    async def test_invalid_transition(self, client: AsyncClient, auth_header, seed_skill):
        # draft -> publish (skip review) should fail
        resp = await client.post("/api/skills/skill-1/publish", headers=auth_header)
        assert resp.status_code == 400

    async def test_submit_review_not_found(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/skills/nonexistent/submit-review", headers=auth_header)
        assert resp.status_code == 404

    async def test_publish_not_found(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/skills/nonexistent/publish", headers=auth_header)
        assert resp.status_code == 404

    async def test_deprecate_not_found(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/skills/nonexistent/deprecate", headers=auth_header)
        assert resp.status_code == 404

    async def test_archive_not_found(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/skills/nonexistent/archive", headers=auth_header)
        assert resp.status_code == 404

    async def test_save_draft(self, client: AsyncClient, auth_header, seed_skill):
        resp = await client.post(
            "/api/skills/skill-1/save-draft",
            json={"description": "Updated description"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "draft"
        assert data["description"] == "Updated description"

    async def test_save_draft_from_review(self, client: AsyncClient, auth_header, seed_skill):
        # move to review first
        await client.post("/api/skills/skill-1/submit-review", headers=auth_header)
        resp = await client.post(
            "/api/skills/skill-1/save-draft",
            json={"description": "Back to draft"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "draft"

    async def test_list_skills_filter_by_status(self, client: AsyncClient, auth_header, seed_skill):
        resp = await client.get("/api/skills?status=draft", headers=auth_header)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        resp = await client.get("/api/skills?status=published", headers=auth_header)
        assert resp.status_code == 200
        assert len(resp.json()) == 0
