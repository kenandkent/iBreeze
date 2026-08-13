"""Coverage-focused tests for ``ibreeze.persistence.connection``.

Exercises bootstrap/read connection opening and the eight-slot ``ReadPool``:
query helpers, read transactions, rollback-on-release, and pool lifecycle.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from ibreeze.persistence.connection import (
    ReadPool,
    _open_read_connection,
    open_bootstrap_connection,
)


async def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "read.db"
    conn = await aiosqlite.connect(str(db_path))
    await conn.execute("CREATE TABLE items (id TEXT PRIMARY KEY, value TEXT)")
    await conn.execute("INSERT INTO items VALUES ('a', 'apple'), ('b', 'banana')")
    await conn.commit()
    await conn.close()
    return db_path


@pytest.mark.asyncio
class TestOpenBootstrapConnection:
    async def test_opens_with_row_factory_and_pragmas(self, tmp_path: Path) -> None:
        db_path = tmp_path / "bootstrap.db"
        conn = await open_bootstrap_connection(db_path)
        try:
            assert conn.row_factory is aiosqlite.Row
            journal = await (await conn.execute("PRAGMA journal_mode")).fetchone()
            assert journal[0] == "wal"
            synchronous = await (await conn.execute("PRAGMA synchronous")).fetchone()
            assert synchronous[0] == 1  # NORMAL
        finally:
            await conn.close()


@pytest.mark.asyncio
class TestOpenReadConnection:
    async def test_query_only_is_enabled(self, tmp_path: Path) -> None:
        db_path = await _make_db(tmp_path)
        conn = await _open_read_connection(db_path)
        try:
            query_only = await (await conn.execute("PRAGMA query_only")).fetchone()
            assert query_only[0] == 1
        finally:
            await conn.close()


@pytest.mark.asyncio
class TestReadPool:
    async def test_init_rejects_wrong_connection_count(self, tmp_path: Path) -> None:
        db_path = await _make_db(tmp_path)
        conn = await aiosqlite.connect(str(db_path))
        try:
            with pytest.raises(ValueError, match="exactly eight"):
                ReadPool((conn, conn))
        finally:
            await conn.close()

    async def test_open_and_query_one(self, tmp_path: Path) -> None:
        db_path = await _make_db(tmp_path)
        pool = await ReadPool.open(db_path)
        try:
            row = await pool.query_one("SELECT * FROM items WHERE id=?", ("a",))
            assert row == {"id": "a", "value": "apple"}
            assert pool._pool.qsize() == 8
        finally:
            await pool.close()

    async def test_query_one_no_rows(self, tmp_path: Path) -> None:
        db_path = await _make_db(tmp_path)
        pool = await ReadPool.open(db_path)
        try:
            result = await pool.query_one("SELECT * FROM items WHERE id=?", ("zzz",))
            assert result is None
        finally:
            await pool.close()

    async def test_query_all(self, tmp_path: Path) -> None:
        db_path = await _make_db(tmp_path)
        pool = await ReadPool.open(db_path)
        try:
            rows = await pool.query_all("SELECT * FROM items ORDER BY id")
            assert rows == [
                {"id": "a", "value": "apple"},
                {"id": "b", "value": "banana"},
            ]
        finally:
            await pool.close()

    async def test_read_transaction(self, tmp_path: Path) -> None:
        db_path = await _make_db(tmp_path)

        async def count(conn: aiosqlite.Connection) -> int:
            cursor = await conn.execute("SELECT count(*) FROM items")
            row = await cursor.fetchone()
            return int(row[0])

        pool = await ReadPool.open(db_path)
        try:
            result = await pool.read_transaction(count)
            assert result == 2
        finally:
            await pool.close()

    async def test_release_rolls_back_in_transaction_connection(self, tmp_path: Path) -> None:
        db_path = await _make_db(tmp_path)
        connections = [await aiosqlite.connect(str(db_path)) for _ in range(8)]
        pool = ReadPool(tuple(connections))
        try:

            async def write_row(c: aiosqlite.Connection) -> None:
                await c.execute("INSERT INTO items VALUES ('c', 'cherry')")

            await pool.read_transaction(write_row)
            cursor = await connections[0].execute("SELECT count(*) FROM items")
            row = await cursor.fetchone()
            assert row[0] == 2  # INSERT was rolled back on release
            assert connections[0].in_transaction is False
            assert pool._pool.qsize() == 8
        finally:
            await pool.close()
