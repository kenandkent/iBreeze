from passlib.hash import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminUser


async def _create_user(db: AsyncSession, user_id: str, username: str, role: str):
    user = AdminUser(
        user_id=user_id,
        username=username,
        password_hash=bcrypt.hash("pass"),
        role=role,
        status="active",
    )
    db.add(user)
    await db.commit()


async def _login(client, username: str = "u1", password: str = "pass"):
    resp = await client.post("/api/auth/login", json={"username": username, "password": password})
    return resp.json()["access_token"]


async def test_super_admin_access_all(client, db_session):
    await _create_user(db_session, "u1", "u1", "super_admin")
    token = await _login(client, "u1")
    for resource in ["capabilities", "knowledge", "providers", "backends", "governance", "audit", "settings"]:
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200


async def test_company_admin_cannot_access_governance(client, db_session):
    await _create_user(db_session, "u2", "u2", "company_admin")
    token = await _login(client, "u2")
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


async def test_viewer_get_me_works(client, db_session):
    await _create_user(db_session, "u3", "u3", "viewer")
    token = await _login(client, "u3")
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


async def test_no_token_returns_401_or_403(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code in (401, 403)


async def test_viewer_cannot_create_capability(client, db_session):
    await _create_user(db_session, "v1", "v1", "viewer")
    token = await _login(client, "v1")
    resp = await client.post(
        "/api/capabilities",
        json={"name": "Test Cap", "company_id": "comp-1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_company_admin_can_create_capability(client, db_session):
    await _create_user(db_session, "ca1", "ca1", "company_admin")
    token = await _login(client, "ca1")
    resp = await client.post(
        "/api/capabilities",
        json={"name": "New Cap", "company_id": "comp-1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "New Cap"


async def test_company_admin_cannot_access_governance_write(client, db_session):
    await _create_user(db_session, "ca2", "ca2", "company_admin")
    token = await _login(client, "ca2")
    resp = await client.post(
        "/api/governance/approval-types",
        json={"company_id": "comp-1", "name": "Test Type"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
