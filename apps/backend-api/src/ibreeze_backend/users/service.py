"""Admin user management service."""

import base64
import json
import uuid
from datetime import UTC, datetime

from passlib.hash import argon2
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.models.token_family import RefreshTokenFamily
from ibreeze_backend.models.user import User
from ibreeze_backend.observability.logging_config import get_logger

logger = get_logger("ibreeze.users.service")

password_hasher = argon2.using(
    type="ID",
    memory_cost=65536,
    rounds=3,
    parallelism=4,
    salt_size=16,
    digest_size=32,
)


async def _get_user_for_update(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id).with_for_update())
    return result.scalar_one_or_none()


async def _revoke_all_user_families(db: AsyncSession, user_id: uuid.UUID, reason: str) -> None:
    now = datetime.now(UTC)
    result = await db.execute(
        select(RefreshTokenFamily)
        .where(
            RefreshTokenFamily.user_id == user_id,
            RefreshTokenFamily.revoked_at.is_(None),
        )
        .with_for_update()
    )
    for family in result.scalars().all():
        family.revoked_at = now
        family.revoke_reason = reason


async def _ensure_identity_available(
    db: AsyncSession,
    *,
    username: str | None,
    email: str | None,
    exclude_user_id: uuid.UUID | None = None,
) -> None:
    if username is not None:
        statement = select(User.id).where(func.lower(User.username) == username.lower())
        if exclude_user_id is not None:
            statement = statement.where(User.id != exclude_user_id)
        if (await db.execute(statement)).scalar_one_or_none() is not None:
            raise ValueError("Username already exists")

    if email is not None:
        statement = select(User.id).where(func.lower(User.email) == email.lower())
        if exclude_user_id is not None:
            statement = statement.where(User.id != exclude_user_id)
        if (await db.execute(statement)).scalar_one_or_none() is not None:
            raise ValueError("Email already exists")


async def create_admin_user(
    db: AsyncSession,
    *,
    user_type: str,
    username: str | None,
    email: str | None,
    display_name: str,
    password: str,
    admin_user: User,
) -> User:
    normalized_username = username.strip() if username is not None else None
    normalized_email = email.strip().lower() if email is not None else None
    await _ensure_identity_available(
        db,
        username=normalized_username,
        email=normalized_email,
    )

    user = User(
        user_type=user_type,
        username=normalized_username,
        email=normalized_email,
        display_name=display_name.strip(),
        password_hash=password_hasher.hash(password),
        status="active",
    )
    db.add(user)
    await db.flush()
    logger.info(
        "create_admin_user_success",
        extra={
            "user_id": str(user.id),
            "user_type": user.user_type,
            "admin_id": str(admin_user.id),
        },
    )
    return user


async def update_admin_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    username: str | None,
    email: str | None,
    display_name: str | None,
    status: str | None,
    admin_user: User,
) -> User:
    user = await _get_user_for_update(db, user_id)
    if user is None:
        raise ValueError("User not found")

    if user.protected and any(value is not None for value in (username, email, status)):
        raise ValueError("Cannot modify protected user")

    if user.user_type == "admin":
        if email is not None:
            raise ValueError("Cannot set email for admin user")
        normalized_username = username.strip() if username is not None else None
        normalized_email = None
    else:
        if username is not None:
            raise ValueError("Cannot set username for app_user")
        normalized_username = None
        normalized_email = email.strip().lower() if email is not None else None

    await _ensure_identity_available(
        db,
        username=normalized_username,
        email=normalized_email,
        exclude_user_id=user.id,
    )

    if normalized_username is not None:
        user.username = normalized_username
    if normalized_email is not None:
        user.email = normalized_email
    if display_name is not None:
        user.display_name = display_name.strip()
    if status is not None and status != user.status:
        user.status = status
        if status == "disabled":
            await _revoke_all_user_families(db, user.id, reason="user_disabled")
    user.version += 1
    user.updated_at = datetime.now(UTC)
    await db.flush()
    logger.info(
        "update_admin_user_success",
        extra={"user_id": str(user.id), "admin_id": str(admin_user.id)},
    )
    return user


async def delete_admin_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    admin_user: User,
) -> None:
    user = await _get_user_for_update(db, user_id)
    if user is None:
        raise ValueError("User not found")
    if user.protected:
        raise ValueError("Cannot delete protected user")

    await _revoke_all_user_families(db, user.id, reason="user_deleted")
    await db.delete(user)
    await db.flush()
    logger.info(
        "delete_admin_user_success",
        extra={"user_id": str(user_id), "admin_id": str(admin_user.id)},
    )


async def reset_password(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    new_password: str,
    admin_user: User,
) -> User:
    user = await _get_user_for_update(db, user_id)
    if user is None:
        raise ValueError("User not found")

    user.password_hash = password_hasher.hash(new_password)
    user.must_change_password = True
    user.version += 1
    user.updated_at = datetime.now(UTC)
    await _revoke_all_user_families(db, user.id, reason="password_reset")
    await db.flush()
    logger.info(
        "reset_password_success",
        extra={"user_id": str(user.id), "admin_id": str(admin_user.id)},
    )
    return user


async def revoke_sessions(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    admin_user: User,
) -> None:
    user = await _get_user_for_update(db, user_id)
    if user is None:
        raise ValueError("User not found")
    await _revoke_all_user_families(db, user.id, reason="admin_revoked")
    logger.info(
        "revoke_sessions_success",
        extra={"user_id": str(user.id), "admin_id": str(admin_user.id)},
    )


async def list_users_admin(
    db: AsyncSession,
    *,
    cursor: str | None,
    limit: int,
    user_type_filter: str | None,
) -> tuple[list[User], str | None, int]:
    count_statement = select(func.count(User.id))
    statement = select(User)
    if user_type_filter is not None:
        count_statement = count_statement.where(User.user_type == user_type_filter)
        statement = statement.where(User.user_type == user_type_filter)

    total = (await db.execute(count_statement)).scalar() or 0
    if cursor is not None:
        try:
            cursor_data = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
            cursor_created_at = datetime.fromisoformat(cursor_data["created_at"])
            cursor_id = uuid.UUID(cursor_data["id"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid cursor") from exc
        statement = statement.where(
            (User.created_at < cursor_created_at) | ((User.created_at == cursor_created_at) & (User.id < cursor_id))
        )

    result = await db.execute(statement.order_by(User.created_at.desc(), User.id.desc()).limit(limit + 1))
    users = list(result.scalars().all())
    next_cursor = None
    if len(users) > limit:
        users = users[:limit]
        last = users[-1]
        next_cursor = base64.urlsafe_b64encode(
            json.dumps(
                {
                    "created_at": last.created_at.isoformat(),
                    "id": str(last.id),
                },
                separators=(",", ":"),
            ).encode("utf-8")
        ).decode("ascii")
    return users, next_cursor, total
