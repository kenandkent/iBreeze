"""乐观锁版本冲突检测测试。"""

from __future__ import annotations

import aiosqlite
import pytest

from acos.store.base_model import BaseModel


async def _setup_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                deleted_at TEXT,
                deleted_by TEXT,
                delete_reason TEXT
            )"""
        )
        await db.execute(
            "INSERT INTO products (name, created_at, updated_at, version) VALUES (?, ?, ?, ?)",
            ("Widget", "2025-01-01T00:00:00Z", "2025-01-01T00:00:00Z", 1),
        )
        await db.commit()


async def test_version_conflict_detection(tmp_path: pytest.TempPathFactory) -> None:
    db_path = str(tmp_path / "lock_test.db")
    await _setup_db(db_path)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT version FROM products WHERE id = 1")
        row = await cursor.fetchone()
        expected_version = row[0]

        result = await db.execute(
            """UPDATE products
               SET name = ?, updated_at = ?, version = version + 1
               WHERE id = ? AND version = ?""",
            ("New Name", "2025-01-02T00:00:00Z", 1, expected_version),
        )
        await db.commit()
        assert result.rowcount == 1

        cursor = await db.execute("SELECT name, version FROM products WHERE id = 1")
        row = await cursor.fetchone()
        assert row[0] == "New Name"
        assert row[1] == 2

        result = await db.execute(
            """UPDATE products
               SET name = ?, updated_at = ?, version = version + 1
               WHERE id = ? AND version = ?""",
            ("Stale Name", "2025-01-03T00:00:00Z", 1, 1),
        )
        await db.commit()
        assert result.rowcount == 0

        cursor = await db.execute("SELECT name, version FROM products WHERE id = 1")
        row = await cursor.fetchone()
        assert row[0] == "New Name"
        assert row[1] == 2


async def test_base_model_default_values() -> None:
    model = BaseModel()
    assert model.version == 1
    assert model.deleted_at is None
    assert model.deleted_by is None
    assert model.delete_reason is None
    assert model.created_at is not None
    assert model.updated_at is not None
