from passlib.hash import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminUser


async def _create_admin(db: AsyncSession, username: str = "testadmin", role: str = "super_admin"):
    user = AdminUser(
        user_id="user-001",
        username=username,
        password_hash=bcrypt.hash("testpass"),
        role=role,
        status="active",
    )
    db.add(user)
    await db.commit()
    return user


async def test_login_success(client, db_session):
    await _create_admin(db_session)
    resp = await client.post("/api/auth/login", json={"username": "testadmin", "password": "testpass"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["username"] == "testadmin"
    assert data["user"]["role"] == "super_admin"


async def test_login_wrong_password(client, db_session):
    await _create_admin(db_session)
    resp = await client.post("/api/auth/login", json={"username": "testadmin", "password": "wrong"})
    assert resp.status_code == 401


async def test_login_nonexistent_user(client):
    resp = await client.post("/api/auth/login", json={"username": "nobody", "password": "pass"})
    assert resp.status_code == 401


async def test_me_with_token(client, db_session):
    await _create_admin(db_session)
    login_resp = await client.post("/api/auth/login", json={"username": "testadmin", "password": "testpass"})
    token = login_resp.json()["access_token"]
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "testadmin"


async def test_me_without_token(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code in (401, 403)


async def test_refresh_success(client, db_session):
    await _create_admin(db_session)
    login_resp = await client.post("/api/auth/login", json={"username": "testadmin", "password": "testpass"})
    refresh_token = login_resp.json()["refresh_token"]
    resp = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_refresh_invalid_token(client):
    resp = await client.post("/api/auth/refresh", json={"refresh_token": "garbage"})
    assert resp.status_code == 401


async def test_login_disabled_account(client, db_session):
    user = AdminUser(
        user_id="user-dis",
        username="disabled_user",
        password_hash=bcrypt.hash("testpass"),
        role="viewer",
        status="disabled",
    )
    db_session.add(user)
    await db_session.commit()
    resp = await client.post("/api/auth/login", json={"username": "disabled_user", "password": "testpass"})
    assert resp.status_code == 401


async def test_refresh_with_access_token(client, db_session):
    await _create_admin(db_session)
    login_resp = await client.post("/api/auth/login", json={"username": "testadmin", "password": "testpass"})
    access_token = login_resp.json()["access_token"]
    resp = await client.post("/api/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401


async def test_me_with_expired_token(client, db_session):
    import time
    from unittest.mock import patch

    from app.auth.jwt import create_access_token

    await _create_admin(db_session)
    token = create_access_token("user-001", "super_admin")

    # Patch datetime to make the token appear expired
    with patch("app.auth.jwt.datetime") as mock_dt:
        import datetime as _dt
        mock_dt.now.return_value = _dt.datetime(2099, 1, 1, tzinfo=_dt.timezone.utc)
        mock_dt.side_effect = _dt.datetime

        # Manually encode an already-expired token
        import jwt as pyjwt
        from app.config import settings

        expire = _dt.datetime(2020, 1, 1, tzinfo=_dt.timezone.utc)
        payload = {"sub": "user-001", "role": "super_admin", "exp": expire, "type": "access"}
        expired_token = pyjwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401
