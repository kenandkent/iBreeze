"""User management service."""
import uuid

from passlib.hash import argon2
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.models.user import User


async def create_user(
    db: AsyncSession,
    username: str,
    email: str,
    password: str,
    role: str = "viewer",
    user_type: str = "app_user",
    protected: bool = False,
    must_change_password: bool = False,
) -> User:
    """Create a new user."""
    user = User(
        username=username,
        email=email,
        hashed_password=argon2.hash(password),
        role=role,
        user_type=user_type,
        protected=protected,
        must_change_password=must_change_password,
    )
    db.add(user)
    await db.flush()
    return user


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Get a user by ID."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    """Get a user by username."""
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def list_users(
    db: AsyncSession, skip: int = 0, limit: int = 100
) -> tuple[list[User], int]:
    """List users with pagination."""
    count_result = await db.execute(select(func.count(User.id)))
    total = count_result.scalar() or 0

    result = await db.execute(select(User).offset(skip).limit(limit))
    users = list(result.scalars().all())
    return users, total


async def update_user(
    db: AsyncSession,
    user: User,
    email: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> User:
    """Update a user."""
    if email is not None:
        user.email = email
    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active
    await db.flush()
    return user


async def delete_user(db: AsyncSession, user: User) -> None:
    """Delete a user."""
    await db.delete(user)
    await db.flush()
