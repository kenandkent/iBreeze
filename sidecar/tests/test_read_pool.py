from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.asyncio
class TestReadPool:
    async def test_start_creates_pool(self, tmp_path: Path):
        db_path = str(tmp_path / "test.db")
        import aiosqlite
        conn = await aiosqlite.connect(db_path)
        await conn.execute("CREATE TABLE test (id INT)")
        await conn.close()

        from ibreeze.persistence.read_pool import ReadPool
        pool = ReadPool(size=2, db_path=db_path)
        await pool.start(db_path)
        try:
            assert len(pool._connections) == 2
            assert pool._pool.qsize() == 2
        finally:
            await pool.stop()

    async def test_acquire_returns_connection(self, tmp_path: Path):
        db_path = str(tmp_path / "test.db")
        import aiosqlite
        conn = await aiosqlite.connect(db_path)
        await conn.execute("CREATE TABLE test (id INT)")
        await conn.close()

        from ibreeze.persistence.read_pool import ReadPool
        pool = ReadPool(size=1, db_path=db_path)
        await pool.start(db_path)
        try:
            async with pool.acquire() as acq:
                assert acq is not None
            assert pool._pool.qsize() == 1
        finally:
            await pool.stop()

    async def test_stop_closes_connections(self, tmp_path: Path):
        db_path = str(tmp_path / "test.db")
        import aiosqlite
        conn = await aiosqlite.connect(db_path)
        await conn.execute("CREATE TABLE test (id INT)")
        await conn.close()

        from ibreeze.persistence.read_pool import ReadPool
        pool = ReadPool(size=1, db_path=db_path)
        await pool.start(db_path)
        await pool.stop()
        assert len(pool._connections) == 0

    async def test_start_with_pragma(self, tmp_path: Path):
        db_path = str(tmp_path / "test.db")
        import aiosqlite
        conn = await aiosqlite.connect(db_path)
        await conn.execute("CREATE TABLE test (id INT)")
        await conn.close()

        from ibreeze.persistence.read_pool import ReadPool
        pool = ReadPool(size=1)
        await pool.start(db_path)
        try:
            async with pool.acquire() as acq:
                cursor = await acq.execute("PRAGMA query_only")
                row = await cursor.fetchone()
                assert row[0] == 1
        finally:
            await pool.stop()
