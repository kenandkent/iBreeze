import pytest
from httpx import AsyncClient

from app.auth.jwt import create_access_token
from app.models.admin import AdminUser
from app.models.template import EmployeeTemplate


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
async def seed_template(db_session):
    template = EmployeeTemplate(
        template_id="template-1",
        company_id="comp-1",
        name="Test Template",
        role="engineer",
        description="A test template",
        provider_id="prov-1",
        capability_id="cap-1",
        model="gpt-4",
        status="draft",
        version="1",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    db_session.add(template)
    await db_session.commit()


class TestTemplatesAPI:
    async def test_list_templates_empty(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/templates", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_template(self, client: AsyncClient, auth_header):
        resp = await client.post(
            "/api/templates",
            json={"company_id": "comp-1", "name": "New Template", "role": "designer"},
            headers=auth_header,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "New Template"
        assert data["status"] == "draft"
        assert data["version"] == "1"

    async def test_get_template(self, client: AsyncClient, auth_header, seed_template):
        resp = await client.get("/api/templates/template-1", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test Template"

    async def test_get_template_not_found(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/templates/nonexistent", headers=auth_header)
        assert resp.status_code == 404

    async def test_update_template(self, client: AsyncClient, auth_header, seed_template):
        resp = await client.put(
            "/api/templates/template-1",
            json={"name": "Updated Template", "role": "senior engineer"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Template"
        assert data["role"] == "senior engineer"

    async def test_update_template_not_found(self, client: AsyncClient, auth_header):
        resp = await client.put(
            "/api/templates/nonexistent",
            json={"name": "X"},
            headers=auth_header,
        )
        assert resp.status_code == 404

    async def test_activate_template(self, client: AsyncClient, auth_header, seed_template):
        resp = await client.post("/api/templates/template-1/activate", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    async def test_activate_template_not_found(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/templates/nonexistent/activate", headers=auth_header)
        assert resp.status_code == 404

    async def test_archive_template(self, client: AsyncClient, auth_header, seed_template):
        # must activate first
        await client.post("/api/templates/template-1/activate", headers=auth_header)
        resp = await client.post("/api/templates/template-1/archive", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    async def test_archive_template_not_found(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/templates/nonexistent/archive", headers=auth_header)
        assert resp.status_code == 404

    async def test_archive_from_draft_fails(self, client: AsyncClient, auth_header, seed_template):
        resp = await client.post("/api/templates/template-1/archive", headers=auth_header)
        assert resp.status_code == 400

    async def test_activate_from_active_fails(self, client: AsyncClient, auth_header, seed_template):
        await client.post("/api/templates/template-1/activate", headers=auth_header)
        resp = await client.post("/api/templates/template-1/activate", headers=auth_header)
        assert resp.status_code == 400

    async def test_activate_from_archived_succeeds(self, client: AsyncClient, auth_header, seed_template):
        await client.post("/api/templates/template-1/activate", headers=auth_header)
        await client.post("/api/templates/template-1/archive", headers=auth_header)
        resp = await client.post("/api/templates/template-1/activate", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    async def test_list_templates_filter_by_status(self, client: AsyncClient, auth_header, seed_template):
        resp = await client.get("/api/templates?status=draft", headers=auth_header)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        resp = await client.get("/api/templates?status=active", headers=auth_header)
        assert resp.status_code == 200
        assert len(resp.json()) == 0
