"""DEPRECATED - 请使用 ibreeze.persistence 模块。

此文件将在此次架构重构中删除。所有新代码必须通过 ApplicationLifecycle
(writer/read_pool/write_queue/unit_of_work) 访问数据库，禁止导入 LocalDB。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from ibreeze.persistence.connection import ReadPool, open_writer

logger = logging.getLogger("ibreeze.local_db")
warnings.warn(
    "LocalDB is DEPRECATED and will be removed. Use ApplicationLifecycle.persistence instead.",
    DeprecationWarning,
    stacklevel=2,
)

SLOW_QUERY_THRESHOLD_MS = 100

DEFAULT_DB_PATH = Path.home() / ".ibreeze" / "profile.db"
MAX_DB_SIZE_BYTES = 100 * 1024 * 1024

# ── PRAGMA 常量（H.1）────────────────────────────────────────────────────

_PRAGMAS = [
    "PRAGMA journal_mode = WAL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA busy_timeout = 5000",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA temp_store = MEMORY",
]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _content_sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


async def execute_with_logging(db: Any, sql: str, params: Any = None) -> Any:
    start = datetime.now(UTC).timestamp()
    if params:
        cursor = await db.execute(sql, params)
    else:
        cursor = await db.execute(sql)
    elapsed_ms = (datetime.now(UTC).timestamp() - start) * 1000
    if elapsed_ms > SLOW_QUERY_THRESHOLD_MS:
        logger.warning("db.slow_query", extra={"elapsed_ms": round(elapsed_ms, 1), "sql_preview": sql[:200]})
    return cursor


class LocalDB:
    """异步 SQLite 数据库：1 写连接 + N 读连接池，WAL 模式。

    已废弃：委托给 persistence.connection.ReadPool 和 persistence.migrator.MigrationRunner。
    请使用 ApplicationLifecycle 或直接使用 persistence 模块。
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        read_pool_size: int = 8,
        *,
        writer: aiosqlite.Connection | None = None,
        read_pool: ReadPool | None = None,
    ) -> None:
        self._db_path = str(db_path or DEFAULT_DB_PATH)
        self._read_pool_size = read_pool_size
        self._writer: aiosqlite.Connection | None = writer
        self._read_pool: ReadPool | None = read_pool
        self._pool_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """打开写连接、填充读连接池。

        已废弃：委托给 persistence.connection.open_writer 和 ReadPool.open。
        """
        if self._writer is not None:
            return
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        self._writer = await open_writer(Path(self._db_path))

        from ibreeze.persistence.migrator import MigrationRunner
        runner = MigrationRunner(self._writer)
        await runner.apply_all()

        self._read_pool = await ReadPool.open(Path(self._db_path))

    async def initialize_profile(
        self,
        *,
        profile_id: str,
        backend_origin: str,
        app_user_id: str,
        masked_identifier: str,
        device_id: str,
        allow_create: bool,
    ) -> None:
        """Create or verify the immutable Profile identity before RPC becomes ready."""
        connection = self.write_connection
        await connection.execute("BEGIN IMMEDIATE")
        try:
            cursor = await connection.execute("SELECT * FROM local_profile LIMIT 2")
            rows = list(await cursor.fetchall())
            now = _now_iso()
            if not rows:
                if not allow_create:
                    raise ValueError("PROFILE_IDENTITY_MISSING")
                await connection.execute(
                    """INSERT INTO local_profile
                       (id,created_by_app_version,backend_origin,app_user_id,
                        masked_identifier,device_id,created_at,last_opened_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        profile_id,
                        "0.0.0",
                        backend_origin,
                        app_user_id,
                        masked_identifier,
                        device_id,
                        now,
                        now,
                    ),
                )
            elif len(rows) != 1:
                raise ValueError("PROFILE_IDENTITY_MISMATCH")
            else:
                row = rows[0]
                if (
                    row["id"] != profile_id
                    or row["backend_origin"] != backend_origin
                    or row["app_user_id"] != app_user_id
                    or row["device_id"] != device_id
                    or (not allow_create and row["masked_identifier"] != masked_identifier)
                ):
                    raise ValueError("PROFILE_IDENTITY_MISMATCH")
                await connection.execute(
                    """UPDATE local_profile
                       SET masked_identifier=?,last_opened_at=?
                       WHERE id=?""",
                    (masked_identifier, now, profile_id),
                )
            await connection.commit()
        except Exception:
            await connection.rollback()
            raise

    @property
    def write_connection(self) -> aiosqlite.Connection:
        if self._writer is None:
            raise RuntimeError("数据库未初始化")
        return self._writer

    @property
    def db_path(self) -> Path:
        return Path(self._db_path)

    async def close(self) -> None:
        if self._writer is not None:
            if self._writer.in_transaction:
                await self._writer.rollback()
            await self._writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            await self._writer.close()
            self._writer = None

    # ── 读连接借出/归还 ──────────────────────────────────────────────────

    async def _acquire_read(self) -> aiosqlite.Connection:
        if self._read_pool is not None:
            return await self._read_pool._acquire()
        conn = await aiosqlite.connect(self._db_path)
        for pragma in _PRAGMAS:
            await conn.execute(pragma)
        return conn

    async def _release_read(self, conn: aiosqlite.Connection) -> None:
        if self._read_pool is not None:
            await self._read_pool._release(conn)
            return
        if conn.in_transaction:
            await conn.rollback()
        await conn.close()

    # ── 写操作 ───────────────────────────────────────────────────────────

    async def execute_write(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Cursor:
        assert self._writer is not None, "数据库未初始化"
        cursor = await self._writer.execute(sql, params)
        await self._writer.commit()
        return cursor

    async def execute_script(self, sql: str) -> None:
        assert self._writer is not None, "数据库未初始化"
        await self._writer.executescript(sql)
        await self._writer.commit()

    async def execute_many_write(self, sql: str, params_list: list[tuple[Any, ...]]) -> None:
        assert self._writer is not None, "数据库未初始化"
        await self._writer.executemany(sql, params_list)
        await self._writer.commit()

    async def execute_write_batch(self, operations: list[tuple[str, tuple[Any, ...]]]) -> list[aiosqlite.Cursor]:
        assert self._writer is not None, "数据库未初始化"
        results: list[aiosqlite.Cursor] = []
        try:
            for sql, params in operations:
                cursor = await self._writer.execute(sql, params)
                results.append(cursor)
            await self._writer.commit()
        except Exception:
            await self._writer.rollback()
            raise
        return results

    # ── 读操作 ───────────────────────────────────────────────────────────

    async def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        if self._read_pool is not None:
            return await self._read_pool.query_one(sql, params)
        conn = await self._acquire_read()
        try:
            cursor = await conn.execute(sql, params)
            row = await cursor.fetchone()
            if row is None:
                return None
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        finally:
            await self._release_read(conn)

    async def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if self._read_pool is not None:
            return await self._read_pool.query_all(sql, params)
        conn = await self._acquire_read()
        try:
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        finally:
            await self._release_read(conn)

    async def fetch_val(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        if self._read_pool is not None:
            result = await self._read_pool.query_one(sql, params)
            if result is None:
                return None
            return next(iter(result.values()))
        conn = await self._acquire_read()
        try:
            cursor = await conn.execute(sql, params)
            row = await cursor.fetchone()
            return row[0] if row else None
        finally:
            await self._release_read(conn)

    # ── 通用 CRUD 便捷方法 ───────────────────────────────────────────────

    async def insert(self, table: str, data: dict[str, Any]) -> dict[str, Any]:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        await self.execute_write(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
            tuple(data.values()),
        )
        return data

    async def get_by_id(self, table: str, id: str) -> dict[str, Any] | None:
        return await self.fetch_one(f"SELECT * FROM {table} WHERE id = ?", (id,))

    async def update_by_id(self, table: str, id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        if not data:
            return await self.get_by_id(table, id)
        set_clause = ", ".join(f"{k} = ?" for k in data.keys())
        await self.execute_write(
            f"UPDATE {table} SET {set_clause} WHERE id = ?",
            tuple(list(data.values()) + [id]),
        )
        return await self.get_by_id(table, id)

    async def delete_by_id(self, table: str, id: str) -> bool:
        cursor = await self.execute_write(f"DELETE FROM {table} WHERE id = ?", (id,))
        return cursor.rowcount > 0

    async def list_all(
        self,
        table: str,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where_parts: list[str] = []
        values: list[Any] = []
        if filters:
            for k, v in filters.items():
                where_parts.append(f"{k} = ?")
                values.append(v)
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        sql = f"SELECT * FROM {table} {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        return await self.fetch_all(sql, tuple(values + [limit, offset]))

    async def count(self, table: str, filters: dict[str, Any] | None = None) -> int:
        where_parts: list[str] = []
        values: list[Any] = []
        if filters:
            for k, v in filters.items():
                where_parts.append(f"{k} = ?")
                values.append(v)
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        result = await self.fetch_val(f"SELECT COUNT(*) FROM {table} {where_sql}", tuple(values))
        return result or 0
