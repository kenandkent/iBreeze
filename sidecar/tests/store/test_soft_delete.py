"""软删除与 QueryBuilder 过滤测试。"""

from __future__ import annotations

import aiosqlite
import pytest

from acos.store.query_builder import QueryBuilder


async def _setup_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY,
                content TEXT NOT NULL,
                deleted_at TEXT
            )"""
        )
        await db.execute(
            "INSERT INTO notes (id, content, deleted_at) VALUES (?, ?, ?)",
            (1, "alive note", None),
        )
        await db.execute(
            "INSERT INTO notes (id, content, deleted_at) VALUES (?, ?, ?)",
            (2, "deleted note", "2025-01-01T00:00:00Z"),
        )
        await db.execute(
            "INSERT INTO notes (id, content, deleted_at) VALUES (?, ?, ?)",
            (3, "another alive note", None),
        )
        await db.commit()


async def test_soft_delete_filters_by_default(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "soft_delete.db")
    await _setup_db(db_path)

    qb = QueryBuilder("notes")
    sql = qb.build_select(columns=["id", "content"])

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(sql)
        rows = await cursor.fetchall()

    assert len(rows) == 2
    ids = [row[0] for row in rows]
    assert 1 in ids
    assert 3 in ids
    assert 2 not in ids


async def test_include_deleted_returns_all(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "soft_delete_all.db")
    await _setup_db(db_path)

    qb = QueryBuilder("notes", include_deleted=True)
    sql = qb.build_select(columns=["id", "content"])

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(sql)
        rows = await cursor.fetchall()

    assert len(rows) == 3
    ids = {row[0] for row in rows}
    assert ids == {1, 2, 3}


async def test_query_builder_with_where(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "qb_where.db")
    await _setup_db(db_path)

    qb = QueryBuilder("notes").where("content LIKE ?", "%alive%")
    sql = qb.build_select(columns=["id", "content"])
    params = qb.get_params()

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()

    assert len(rows) == 2
