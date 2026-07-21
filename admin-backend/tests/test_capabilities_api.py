import pytest
from httpx import AsyncClient

from app.auth.jwt import create_access_token
from app.models.admin import AdminUser
from app.models.capability import Capability


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
async def seed_capability(db_session):
    cap = Capability(
        capability_id="cap-1",
        company_id="comp-1",
        name="Test Capability",
        status="draft",
        current_version=1,
        version=1,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    db_session.add(cap)
    await db_session.commit()


@pytest.mark.usefixtures("seed_capability")
class TestCapabilitiesAPI:
    async def test_list(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/capabilities", headers=auth_header)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_create(self, client: AsyncClient, auth_header):
        resp = await client.post(
            "/api/capabilities",
            json={"name": "New Cap", "company_id": "comp-1"},
            headers=auth_header,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "New Cap"
        assert data["status"] == "draft"

    async def test_get(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/capabilities/cap-1", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test Capability"

    async def test_get_not_found(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/capabilities/nonexistent", headers=auth_header)
        assert resp.status_code == 404

    async def test_update(self, client: AsyncClient, auth_header):
        resp = await client.put(
            "/api/capabilities/cap-1",
            json={"name": "Updated"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"

    async def test_submit_review(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/capabilities/cap-1/submit-review", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "review"

    async def test_publish(self, client: AsyncClient, auth_header, db_session):
        cap = (await db_session.execute(
            __import__("sqlalchemy").select(Capability).where(Capability.capability_id == "cap-1")
        )).scalar_one()
        cap.status = "review"
        await db_session.commit()

        resp = await client.post("/api/capabilities/cap-1/publish", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "published"

    async def test_invalid_transition(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/capabilities/cap-1/publish", headers=auth_header)
        assert resp.status_code == 400

    async def test_deprecate(self, client: AsyncClient, auth_header, db_session):
        cap = (await db_session.execute(
            __import__("sqlalchemy").select(Capability).where(Capability.capability_id == "cap-1")
        )).scalar_one()
        cap.status = "published"
        await db_session.commit()

        resp = await client.post("/api/capabilities/cap-1/deprecate", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "deprecated"

    async def test_archive(self, client: AsyncClient, auth_header, db_session):
        cap = (await db_session.execute(
            __import__("sqlalchemy").select(Capability).where(Capability.capability_id == "cap-1")
        )).scalar_one()
        cap.status = "deprecated"
        await db_session.commit()

        resp = await client.post("/api/capabilities/cap-1/archive", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    async def test_versions(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/capabilities/cap-1/versions", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_version(self, client: AsyncClient, auth_header):
        resp = await client.post(
            "/api/capabilities/cap-1/versions",
            json={"content": {"key": "value"}},
            headers=auth_header,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["version"] == 2
        assert data["content"] == {"key": "value"}

    async def test_bindings(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/capabilities/cap-1/bindings", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_binding(self, client: AsyncClient, auth_header):
        resp = await client.post(
            "/api/capabilities/cap-1/bindings",
            json={"skill_id": "skill-1", "ordinal": 0},
            headers=auth_header,
        )
        assert resp.status_code == 201
        assert resp.json()["skill_id"] == "skill-1"

    async def test_no_auth(self, client: AsyncClient):
        resp = await client.get("/api/capabilities")
        assert resp.status_code in (401, 403)

    async def test_viewer_cannot_write(self, client: AsyncClient, db_session):
        user = AdminUser(
            user_id="viewer-1",
            username="viewer",
            password_hash="x",
            role="viewer",
            status="active",
        )
        db_session.add(user)
        await db_session.commit()
        from app.auth.jwt import create_access_token
        token = create_access_token("viewer-1", "viewer")
        resp = await client.post(
            "/api/capabilities",
            json={"name": "X"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
