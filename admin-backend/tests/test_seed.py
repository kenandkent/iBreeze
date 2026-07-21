from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminUser
from app.seed import seed_admin_user


async def test_seed_creates_admin(db_session: AsyncSession):
    await seed_admin_user(db_session)
    result = await db_session.execute(select(AdminUser).where(AdminUser.username == "admin"))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.role == "super_admin"
    assert user.status == "active"


async def test_seed_idempotent(db_session: AsyncSession):
    await seed_admin_user(db_session)
    await seed_admin_user(db_session)
    result = await db_session.execute(select(AdminUser).where(AdminUser.username == "admin"))
    users = result.scalars().all()
    assert len(users) == 1


async def test_seed_default_password_works(client, db_session):
    await seed_admin_user(db_session)
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == "super_admin"


async def test_seed_preserves_other_users(db_session: AsyncSession):
    custom = AdminUser(
        user_id="user-custom",
        username="custom_user",
        password_hash="x",
        role="viewer",
        status="active",
    )
    db_session.add(custom)
    await db_session.commit()

    await seed_admin_user(db_session)

    result = await db_session.execute(select(AdminUser).where(AdminUser.username == "custom_user"))
    assert result.scalar_one_or_none() is not None

    result2 = await db_session.execute(select(AdminUser).where(AdminUser.username == "admin"))
    assert result2.scalar_one_or_none() is not None
