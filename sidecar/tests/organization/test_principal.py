"""本机身份主体测试。"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from acos.organization.principal import (
    get_local_owner,
    reset_local_owner_cache,
    resolve_actor,
)
from acos.store.migrator import Migrator


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    reset_local_owner_cache()
    yield
    reset_local_owner_cache()


@pytest.fixture
async def conn(tmp_path: Path) -> aiosqlite.Connection:
    db_path = tmp_path / "test.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(str(Path(__file__).resolve().parents[2] / "migrations"))
    db = await aiosqlite.connect(str(db_path))
    db.row_factory = aiosqlite.Row
    return db


async def test_get_local_owner_creates(conn: aiosqlite.Connection) -> None:
    owner = await get_local_owner(conn)
    assert owner.owner_id
    assert owner.display_name == "Local Owner"

    cursor = await conn.execute("SELECT COUNT(*) FROM local_owner")
    row = await cursor.fetchone()
    assert row[0] == 1


async def test_get_local_owner_returns_same_id(conn: aiosqlite.Connection) -> None:
    first = await get_local_owner(conn)
    second = await get_local_owner(conn)
    assert first.owner_id == second.owner_id


async def test_resolve_actor_local_owner(conn: aiosqlite.Connection) -> None:
    actor_type, actor_id = await resolve_actor(conn, None)
    assert actor_type == "local_owner"
    assert actor_id

    actor_type2, actor_id2 = await resolve_actor(conn, {})
    assert actor_type2 == "local_owner"
    assert actor_id2 == actor_id


async def test_resolve_actor_assignment(conn: aiosqlite.Connection) -> None:
    context = {"actor_type": "assignment", "actor_id": "assign-001"}
    actor_type, actor_id = await resolve_actor(conn, context)
    assert actor_type == "assignment"
    assert actor_id == "assign-001"


async def test_reset_cache(tmp_path: Path) -> None:
    db_path = tmp_path / "test2.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(str(Path(__file__).resolve().parents[2] / "migrations"))
    async with aiosqlite.connect(str(db_path)) as db:
        first = await get_local_owner(db)
        reset_local_owner_cache()
        second = await get_local_owner(db)
        assert first.owner_id == second.owner_id
