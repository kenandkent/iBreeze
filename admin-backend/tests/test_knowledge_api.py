import pytest
from httpx import AsyncClient

from app.auth.jwt import create_access_token
from app.models.admin import AdminUser
from app.models.knowledge import KnowledgeDocument


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
async def seed_doc(db_session):
    doc = KnowledgeDocument(
        knowledge_id="doc-1",
        company_id="comp-1",
        title="Test Doc",
        content="Some content",
        status="active",
        governance_confirmed=0,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    db_session.add(doc)
    await db_session.commit()


@pytest.mark.usefixtures("seed_doc")
class TestKnowledgeAPI:
    async def test_list_documents(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/knowledge/documents", headers=auth_header)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_get_document(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/knowledge/documents/doc-1", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["title"] == "Test Doc"

    async def test_get_not_found(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/knowledge/documents/nonexistent", headers=auth_header)
        assert resp.status_code == 404

    async def test_create_document(self, client: AsyncClient, auth_header):
        resp = await client.post(
            "/api/knowledge/documents",
            json={"company_id": "comp-1", "title": "New Doc"},
            headers=auth_header,
        )
        assert resp.status_code == 201
        assert resp.json()["title"] == "New Doc"

    async def test_update_document(self, client: AsyncClient, auth_header):
        resp = await client.put(
            "/api/knowledge/documents/doc-1",
            json={"title": "Updated"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated"

    async def test_delete_document(self, client: AsyncClient, auth_header):
        resp = await client.delete("/api/knowledge/documents/doc-1", headers=auth_header)
        assert resp.status_code == 204

    async def test_confirm_document(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/knowledge/documents/doc-1/confirm", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["governance_confirmed"] == 1

    async def test_reject_document(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/knowledge/documents/doc-1/reject", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["governance_confirmed"] == -1

    async def test_reindex(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/knowledge/reindex", headers=auth_header)
        assert resp.status_code == 200

    async def test_delete_source(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/knowledge/sources/src-1/delete", headers=auth_header)
        assert resp.status_code == 200

    async def test_retry_ingest(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/knowledge/ingest/job-1/retry", headers=auth_header)
        assert resp.status_code == 200
