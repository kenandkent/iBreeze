import pytest
from httpx import AsyncClient

from app.auth.jwt import create_access_token
from app.models.admin import AdminUser
from app.models.capability import PromptAsset


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
async def seed_prompt(db_session):
    prompt = PromptAsset(
        prompt_id="prompt-1",
        company_id="comp-1",
        name="Test Prompt",
        description="A test prompt",
        content="You are a helpful assistant.",
        status="draft",
        version=1,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    db_session.add(prompt)
    await db_session.commit()


class TestPromptsAPI:
    async def test_list_prompts_empty(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/prompts", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_prompt(self, client: AsyncClient, auth_header):
        resp = await client.post(
            "/api/prompts",
            json={"company_id": "comp-1", "name": "New Prompt", "content": "Hello"},
            headers=auth_header,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "New Prompt"
        assert data["status"] == "draft"
        assert data["version"] == 1

    async def test_get_prompt(self, client: AsyncClient, auth_header, seed_prompt):
        resp = await client.get("/api/prompts/prompt-1", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test Prompt"

    async def test_get_prompt_not_found(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/prompts/nonexistent", headers=auth_header)
        assert resp.status_code == 404

    async def test_update_prompt(self, client: AsyncClient, auth_header, seed_prompt):
        resp = await client.put(
            "/api/prompts/prompt-1",
            json={"name": "Updated Prompt"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Prompt"
        assert data["version"] == 2

    async def test_update_prompt_not_found(self, client: AsyncClient, auth_header):
        resp = await client.put(
            "/api/prompts/nonexistent",
            json={"name": "X"},
            headers=auth_header,
        )
        assert resp.status_code == 404

    async def test_state_transitions(self, client: AsyncClient, auth_header, seed_prompt):
        # draft -> review
        resp = await client.post("/api/prompts/prompt-1/submit-review", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "review"

        # review -> published
        resp = await client.post("/api/prompts/prompt-1/publish", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "published"

        # published -> deprecated
        resp = await client.post("/api/prompts/prompt-1/deprecate", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "deprecated"

        # deprecated -> archived
        resp = await client.post("/api/prompts/prompt-1/archive", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    async def test_invalid_transition(self, client: AsyncClient, auth_header, seed_prompt):
        # draft -> publish (skip review) should fail
        resp = await client.post("/api/prompts/prompt-1/publish", headers=auth_header)
        assert resp.status_code == 400

    async def test_submit_review_not_found(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/prompts/nonexistent/submit-review", headers=auth_header)
        assert resp.status_code == 404

    async def test_publish_not_found(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/prompts/nonexistent/publish", headers=auth_header)
        assert resp.status_code == 404

    async def test_deprecate_not_found(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/prompts/nonexistent/deprecate", headers=auth_header)
        assert resp.status_code == 404

    async def test_archive_not_found(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/prompts/nonexistent/archive", headers=auth_header)
        assert resp.status_code == 404

    async def test_save_draft(self, client: AsyncClient, auth_header, seed_prompt):
        resp = await client.post(
            "/api/prompts/prompt-1/save-draft",
            json={"content": "Updated content"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "draft"
        assert data["content"] == "Updated content"

    async def test_save_draft_from_review(self, client: AsyncClient, auth_header, seed_prompt):
        # move to review first
        await client.post("/api/prompts/prompt-1/submit-review", headers=auth_header)
        resp = await client.post(
            "/api/prompts/prompt-1/save-draft",
            json={"content": "Back to draft"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "draft"

    async def test_list_prompts_filter_by_status(self, client: AsyncClient, auth_header, seed_prompt):
        resp = await client.get("/api/prompts?status=draft", headers=auth_header)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        resp = await client.get("/api/prompts?status=published", headers=auth_header)
        assert resp.status_code == 200
        assert len(resp.json()) == 0
