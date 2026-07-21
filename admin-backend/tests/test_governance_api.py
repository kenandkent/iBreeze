import pytest
from httpx import AsyncClient

from app.auth.jwt import create_access_token
from app.models.admin import AdminUser
from app.models.governance import ApprovalType, KnowledgeRule


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
async def seed_approval_type(db_session):
    at = ApprovalType(
        type_id="type-1",
        company_id="comp-1",
        name="Knowledge Approval",
        description="Approve knowledge documents",
        config={"auto_approve": False},
        version="1",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    db_session.add(at)
    await db_session.commit()


@pytest.mark.usefixtures("seed_approval_type")
class TestGovernanceAPI:
    async def test_list_approval_types(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/governance/approval-types", headers=auth_header)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_create_approval_type(self, client: AsyncClient, auth_header):
        resp = await client.post(
            "/api/governance/approval-types",
            json={"company_id": "comp-1", "name": "Budget Approval"},
            headers=auth_header,
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Budget Approval"

    async def test_update_approval_type(self, client: AsyncClient, auth_header):
        resp = await client.put(
            "/api/governance/approval-types/type-1",
            json={"name": "Updated Type"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Type"

    async def test_list_approvals(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/governance/approvals", headers=auth_header)
        assert resp.status_code == 200

    async def test_get_approval_not_found(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/governance/approvals/nonexistent", headers=auth_header)
        assert resp.status_code == 404

    async def test_delete_approval_type(self, client: AsyncClient, auth_header):
        resp = await client.delete("/api/governance/approval-types/type-1", headers=auth_header)
        assert resp.status_code == 204

    async def test_delete_approval_type_not_found(self, client: AsyncClient, auth_header):
        resp = await client.delete("/api/governance/approval-types/nonexistent", headers=auth_header)
        assert resp.status_code == 404


@pytest.fixture
async def seed_knowledge_rule(db_session):
    rule = KnowledgeRule(
        rule_id="rule-1",
        company_id="comp-1",
        name="Auto Approve Internal",
        description="Auto approve internal docs",
        category="internal",
        action="auto_approve",
        enabled=1,
        config={},
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    db_session.add(rule)
    await db_session.commit()


@pytest.mark.usefixtures("seed_knowledge_rule")
class TestKnowledgeRulesAPI:
    async def test_list_knowledge_rules(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/governance/knowledge-rules", headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Auto Approve Internal"

    async def test_create_knowledge_rule(self, client: AsyncClient, auth_header):
        resp = await client.post(
            "/api/governance/knowledge-rules",
            json={"company_id": "comp-1", "name": "Manual Review", "action": "manual_review"},
            headers=auth_header,
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Manual Review"

    async def test_update_knowledge_rule(self, client: AsyncClient, auth_header):
        resp = await client.put(
            "/api/governance/knowledge-rules/rule-1",
            json={"name": "Updated Rule", "enabled": 0},
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Rule"
        assert data["enabled"] == 0

    async def test_delete_knowledge_rule(self, client: AsyncClient, auth_header):
        resp = await client.delete("/api/governance/knowledge-rules/rule-1", headers=auth_header)
        assert resp.status_code == 204

    async def test_delete_knowledge_rule_not_found(self, client: AsyncClient, auth_header):
        resp = await client.delete("/api/governance/knowledge-rules/nonexistent", headers=auth_header)
        assert resp.status_code == 404
