import pytest
from httpx import AsyncClient

from app.auth.jwt import create_access_token
from app.models.admin import AdminUser
from app.models.provider import Provider


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
async def seed_provider(db_session):
    p = Provider(
        provider_id="prov-1",
        company_id="comp-1",
        name="OpenAI",
        provider_type="openai",
        config={},
        status="active",
        version="1",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    db_session.add(p)
    await db_session.commit()


@pytest.mark.usefixtures("seed_provider")
class TestProvidersAPI:
    async def test_list(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/providers", headers=auth_header)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_create(self, client: AsyncClient, auth_header):
        resp = await client.post(
            "/api/providers",
            json={"name": "Anthropic", "provider_type": "anthropic"},
            headers=auth_header,
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Anthropic"

    async def test_list_models(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/providers/prov-1/models", headers=auth_header)
        assert resp.status_code == 200

    async def test_fetch_models(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/providers/prov-1/fetch-models", headers=auth_header)
        assert resp.status_code == 200

    async def test_set_credentials(self, client: AsyncClient, auth_header):
        resp = await client.put(
            "/api/providers/prov-1/credentials",
            json={"credential_type": "api_key", "credential_ref": "sk-xxx"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.json()["credential_type"] == "api_key"

    async def test_delete_credentials(self, client: AsyncClient, auth_header):
        resp = await client.delete("/api/providers/prov-1/credentials", headers=auth_header)
        assert resp.status_code == 200

    async def test_probe(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/providers/prov-1/probe", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["reachable"] is True

    async def test_update_pricing(self, client: AsyncClient, auth_header):
        resp = await client.put(
            "/api/providers/prov-1/pricing",
            json={"pricing": {"input": 0.01}, "currency": "USD"},
            headers=auth_header,
        )
        assert resp.status_code == 200

    async def test_update_tier_mapping(self, client: AsyncClient, auth_header):
        resp = await client.put(
            "/api/providers/prov-1/tier-mapping",
            json={"tier": "premium", "model_id": "gpt-4"},
            headers=auth_header,
        )
        assert resp.status_code == 200

    async def test_get_by_id(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/providers/prov-1", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["provider_id"] == "prov-1"
        assert resp.json()["name"] == "OpenAI"

    async def test_get_by_id_not_found(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/providers/nonexistent", headers=auth_header)
        assert resp.status_code == 404

    async def test_enable_provider(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/providers/prov-1/enable", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "enabled"

    async def test_disable_provider(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/providers/prov-1/disable", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"

    async def test_enable_not_found(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/providers/nonexistent/enable", headers=auth_header)
        assert resp.status_code == 404
