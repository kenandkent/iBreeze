import pytest
from httpx import AsyncClient

from app.auth.jwt import create_access_token
from app.models.admin import AdminUser
from app.models.capability import Capability
from app.models.knowledge import KnowledgePolicy


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
async def seed_sync_data(db_session):
    cap = Capability(
        capability_id="cap-1",
        company_id="comp-1",
        name="Test Cap",
        status="draft",
        current_version=1,
        version=1,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    policy = KnowledgePolicy(
        company_id="comp-1",
        version=1,
        config={"auto_confirm": True},
        status="active",
        created_at="2026-01-01T00:00:00Z",
    )
    db_session.add_all([cap, policy])
    await db_session.commit()


@pytest.mark.usefixtures("seed_sync_data")
class TestSyncAPI:
    async def test_sync_config(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/sync/config?company_id=comp-1", headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert "timestamp" in data
        assert len(data["capabilities"]) == 1
        assert data["capabilities"][0]["name"] == "Test Cap"
        assert len(data["knowledge_policies"]) == 1

    async def test_sync_config_missing_company(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/sync/config", headers=auth_header)
        assert resp.status_code in (400, 422)

    async def test_sync_config_empty_company(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/sync/config?company_id=nonexistent", headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert "timestamp" in data
        assert data["capabilities"] == []
        assert data["knowledge_policies"] == []

    async def test_sync_config_requires_company_id(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/sync/config", headers=auth_header)
        assert resp.status_code in (400, 422)
