"""本机唯一身份主体。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

import aiosqlite


@dataclass(frozen=True)
class LocalOwnerPrincipal:
    """本机唯一身份主体。"""

    owner_id: str
    display_name: str


_local_owner: Optional[LocalOwnerPrincipal] = None


async def get_local_owner(conn: aiosqlite.Connection) -> LocalOwnerPrincipal:
    """获取本机唯一身份主体，首次调用时自动创建。"""
    global _local_owner
    if _local_owner is not None:
        return _local_owner

    cursor = await conn.execute("SELECT owner_id, display_name FROM local_owner LIMIT 1")
    row = await cursor.fetchone()

    if row is None:
        owner_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO local_owner (owner_id, display_name) VALUES (?, ?)",
            (owner_id, "Local Owner"),
        )
        await conn.commit()
        _local_owner = LocalOwnerPrincipal(owner_id=owner_id, display_name="Local Owner")
    else:
        _local_owner = LocalOwnerPrincipal(owner_id=row[0], display_name=row[1])

    return _local_owner


def reset_local_owner_cache() -> None:
    """重置单例缓存（测试用）。"""
    global _local_owner
    _local_owner = None


async def resolve_actor(
    conn: aiosqlite.Connection, context: dict | None = None
) -> tuple[str, str]:
    """解析 actor 身份，返回 (actor_type, actor_id)。

    UI 发起的管理操作返回 local_owner；Agent 执行任务返回 assignment。
    """
    if context and context.get("actor_type") == "assignment":
        return ("assignment", context["actor_id"])

    owner = await get_local_owner(conn)
    return ("local_owner", owner.owner_id)
