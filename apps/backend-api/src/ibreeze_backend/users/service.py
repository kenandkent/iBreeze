"""Admin user management service."""
import base64
import json
import uuid
from datetime import datetime

from passlib.hash import argon2
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.models.token_family import RefreshTokenFamily as TokenFamily
from ibreeze_backend.models.user import User


async def _revoke_all_user_families(db: AsyncSession, user_id: uuid.UUID) -> None:
    result = await db.execute(
        select(TokenFamily).where(
            TokenFamily.user_id == user_id,
            TokenFamily.status == "active",
        )
    )
    for family in result.scalars().all():
        family.status = "revoked"


async def create_admin_user(
    db: AsyncSession,
    email: str,
    password: str,
    user_type: str,
    admin_user: User,
) -> User:
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise ValueError("Email already exists")

    base_username = email.split("@")[0][:64]
    username = base_username
    counter = 1
    while True:
        result = await db.execute(select(User).where(User.username == username))
        if not result.scalar_one_or_none():
            break
        username = f"{base_username[:58]}_{counter}"[:64]
        counter += 1

    user = User(
        username=username,
        email=email,
        hashed_password=argon2.hash(password),
        user_type=user_type,
    )
    db.add(user)
    await db.flush()
    return user


async def update_admin_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    email: str | None,
    role: str | None,
    is_active: bool | None,
    admin_user: User,
) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("User not found")

    if user.protected:
        if email is not None and email != user.email:
            raise ValueError("Cannot modify protected user")
        if role is not None and role != user.role:
            raise ValueError("Cannot modify protected user")
        if is_active is not None and is_active != user.is_active:
            raise ValueError("Cannot modify protected user")

    if user.user_type == "app_user":
        if role is not None:
            raise ValueError("Cannot change role for app_user")
        if is_active is not None:
            raise ValueError("Cannot change is_active for app_user")

    if email is not None:
        user.email = email
    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active

    await db.flush()
    return user


async def delete_admin_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    admin_user: User,
) -> None:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("User not found")
    if user.protected:
        raise ValueError("Cannot delete protected user")
    await db.delete(user)
    await db.flush()


async def reset_password(
    db: AsyncSession,
    user_id: uuid.UUID,
    new_password: str,
    admin_user: User,
) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("User not found")

    user.hashed_password = argon2.hash(new_password)
    await _revoke_all_user_families(db, user_id)
    await db.flush()
    return user


async def revoke_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    admin_user: User,
) -> bool:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("User not found")
    await _revoke_all_user_families(db, user_id)
    return True


async def list_users_admin(
    db: AsyncSession,
    cursor: str | None,
    limit: int,
    user_type_filter: str | None,
) -> tuple[list[User], str | None, int]:
    count_stmt = select(func.count(User.id))
    if user_type_filter:
        count_stmt = count_stmt.where(User.user_type == user_type_filter)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    stmt = select(User)
    if user_type_filter:
        stmt = stmt.where(User.user_type == user_type_filter)
    if cursor:
        cursor_data = json.loads(base64.b64decode(cursor))
        cursor_dt = datetime.fromisoformat(cursor_data["created_at"])
        cursor_id = uuid.UUID(cursor_data["id"])
        stmt = stmt.where(
            (User.created_at < cursor_dt)
            | ((User.created_at == cursor_dt) & (User.id < cursor_id))
        )
    stmt = stmt.order_by(User.created_at.desc(), User.id.desc()).limit(limit + 1)
    result = await db.execute(stmt)
    users = list(result.scalars().all())

    next_cursor = None
    if len(users) > limit:
        users = users[:limit]
        last = users[-1]
        next_cursor = base64.b64encode(
            json.dumps(
                {"created_at": last.created_at.isoformat(), "id": str(last.id)}
            ).encode()
        ).decode()

    return users, next_cursor, total
