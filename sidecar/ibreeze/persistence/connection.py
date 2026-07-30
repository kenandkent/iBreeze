from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

import aiosqlite

_T = TypeVar("_T")

_BOOTSTRAP_PRAGMAS = [
    "PRAGMA journal_mode = WAL",
    "PRAGMA foreign_keys = OFF",
    "PRAGMA busy_timeout = 5000",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA temp_store = MEMORY",
]

_RUN_PRAGMAS = [
    "PRAGMA journal_mode = WAL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA busy_timeout = 5000",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA temp_store = MEMORY",
    "PRAGMA defer_foreign_keys = OFF",
]


async def open_bootstrap_connection(path: Path) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(str(path), check_same_thread=False)
    conn.row_factory = aiosqlite.Row
    for pragma in _BOOTSTRAP_PRAGMAS:
        await conn.execute(pragma)
    return conn


async def open_writer(path: Path) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(str(path), check_same_thread=False)
    conn.row_factory = aiosqlite.Row
    for pragma in _RUN_PRAGMAS:
        await conn.execute(pragma)
    await conn.execute("PRAGMA wal_autocheckpoint=1000")
    return conn


async def _open_read_connection(path: Path) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(str(path), check_same_thread=False)
    conn.row_factory = aiosqlite.Row
    for pragma in _RUN_PRAGMAS:
        await conn.execute(pragma)
    return conn


class ReadPool:
    def __init__(self, connections: tuple[aiosqlite.Connection, ...]) -> None:
        if len(connections) != 8:
            raise ValueError("read pool requires exactly eight connections")
        self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue(maxsize=8)
        self._connections = list(connections)
        for conn in connections:
            self._pool.put_nowait(conn)

    @classmethod
    async def open(cls, path: Path) -> ReadPool:
        connections: list[aiosqlite.Connection] = []
        for _ in range(8):
            conn = await _open_read_connection(path)
            connections.append(conn)
        return cls(tuple(connections))

    async def close(self) -> None:
        while not self._pool.empty():
            conn = await self._pool.get()
            await conn.close()

    async def _acquire(self) -> aiosqlite.Connection:
        return await self._pool.get()

    async def _release(self, conn: aiosqlite.Connection) -> None:
        if conn.in_transaction:
            await conn.rollback()
        self._pool.put_nowait(conn)

    async def query_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        conn = await self._acquire()
        try:
            cursor = await conn.execute(sql, params)
            row = await cursor.fetchone()
            if row is None:
                return None
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        finally:
            await self._release(conn)

    async def query_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        conn = await self._acquire()
        try:
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        finally:
            await self._release(conn)

    async def read_transaction(self, callback: Callable[[aiosqlite.Connection], Awaitable[_T]]) -> _T:
        conn = await self._acquire()
        try:
            return await callback(conn)
        finally:
            await self._release(conn)
