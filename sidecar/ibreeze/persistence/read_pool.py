import asyncio
from collections.abc import AsyncIterator

import aiosqlite


class ReadPool:
    def __init__(self, size: int = 8, db_path: str = "") -> None:
        self._size = size
        self._db_path = db_path
        self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue(maxsize=size)
        self._connections: list[aiosqlite.Connection] = []

    async def start(self, db_path: str) -> None:
        self._db_path = db_path
        for _ in range(self._size):
            conn = await aiosqlite.connect(db_path)
            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.execute("PRAGMA query_only = ON")
            await conn.execute("PRAGMA defer_foreign_keys = 0")
            self._connections.append(conn)
            await self._pool.put(conn)

    async def stop(self) -> None:
        for conn in self._connections:
            await conn.close()
        self._connections.clear()

    async def acquire(self) -> AsyncIterator[aiosqlite.Connection]:
        conn = await self._pool.get()
        try:
            yield conn
        finally:
            await self._pool.put(conn)
