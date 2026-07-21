import pytest
from httpx import AsyncClient

from app.auth.jwt import create_access_token
from app.models.admin import AdminUser
from app.models.backend import Backend


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
async def seed_backend(db_session):
    b = Backend(
        backend_id="be-1",
        company_id="comp-1",
        name="Local Dev",
        backend_type="local_process",
        status="disabled",
        concurrency=1,
        version="1",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    db_session.add(b)
    await db_session.commit()


@pytest.mark.usefixtures("seed_backend")
class TestBackendsAPI:
    async def test_list(self, client: AsyncClient, auth_header):
        resp = await client.get("/api/backends", headers=auth_header)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_create(self, client: AsyncClient, auth_header):
        resp = await client.post(
            "/api/backends",
            json={"company_id": "comp-1", "name": "New Backend"},
            headers=auth_header,
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "disabled"

    async def test_enable(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/backends/be-1/enable", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "enabled"

    async def test_drain(self, client: AsyncClient, auth_header, db_session):
        b = (await db_session.execute(
            __import__("sqlalchemy").select(Backend).where(Backend.backend_id == "be-1")
        )).scalar_one()
        b.status = "enabled"
        await db_session.commit()

        resp = await client.post("/api/backends/be-1/drain", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "draining"

    async def test_disable(self, client: AsyncClient, auth_header, db_session):
        b = (await db_session.execute(
            __import__("sqlalchemy").select(Backend).where(Backend.backend_id == "be-1")
        )).scalar_one()
        b.status = "enabled"
        await db_session.commit()

        resp = await client.post("/api/backends/be-1/disable", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"

    async def test_invalid_transition(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/backends/be-1/drain", headers=auth_header)
        assert resp.status_code == 400

    async def test_archive(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/backends/be-1/archive", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    async def test_probe(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/backends/be-1/probe", headers=auth_header)
        assert resp.status_code == 200

    async def test_set_default(self, client: AsyncClient, auth_header, db_session):
        b = (await db_session.execute(
            __import__("sqlalchemy").select(Backend).where(Backend.backend_id == "be-1")
        )).scalar_one()
        b.status = "enabled"
        await db_session.commit()

        resp = await client.post("/api/backends/be-1/set-default", headers=auth_header)
        assert resp.status_code == 200

    async def test_set_default_not_enabled(self, client: AsyncClient, auth_header):
        resp = await client.post("/api/backends/be-1/set-default", headers=auth_header)
        assert resp.status_code == 400
