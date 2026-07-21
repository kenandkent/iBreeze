import pytest
from httpx import AsyncClient

from app.auth.jwt import create_access_token
from app.models.admin import AdminUser
from app.models.governance import AuditLog


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
async def seed_audit(db_session):
    log = AuditLog(
        log_id="log-1",
        company_id="comp-1",
        audit_type="action",
        actor_id="user-1",
        action="create_capability",
        resource_type="capability",
        resource_id="cap-1",
        details={"name": "Test"},
        created_at="2026-01-01T00:00:00Z",
    )
    intervention = AuditLog(
        log_id="log-2",
        company_id="comp-1",
        audit_type="intervention",
        actor_id="admin-1",
        action="reject_knowledge",
        resource_type="knowledge",
        resource_id="doc-1",
        details={"reason": "spam"},
        created_at="2026-01-01T00:00:00Z",
    )
    db_session.add_all([log, intervention])
    await db_session.commit()


@pytest.mark.usefixtures("seed_audit")
class TestAuditAPI:
    async def test_list_logs(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/audit/logs", headers=auth_header)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_list_logs_by_type(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/audit/logs?audit_type=action", headers=auth_header)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_list_interventions(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/audit/interventions", headers=auth_header)
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["action"] == "reject_knowledge"
