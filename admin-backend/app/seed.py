import uuid

from passlib.hash import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminUser


async def seed_admin_user(db: AsyncSession) -> None:
    result = await db.execute(select(AdminUser).where(AdminUser.username == "admin"))
    if result.scalar_one_or_none():
        return

    admin = AdminUser(
        user_id=str(uuid.uuid4()),
        username="admin",
        password_hash=bcrypt.hash("admin123"),
        role="super_admin",
        status="active",
    )
    db.add(admin)
    await db.commit()
