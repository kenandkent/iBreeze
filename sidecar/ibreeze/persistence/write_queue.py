import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import aiosqlite

T = TypeVar("T")


class WriteQueue:
    def __init__(self, capacity: int = 32) -> None:
        self._queue: asyncio.Queue[
            tuple[Callable[[aiosqlite.Connection], Awaitable[T]], asyncio.Future[T]]
        ] = asyncio.Queue(maxsize=capacity)
        self._worker_task: asyncio.Task[None] | None = None
        self._db: aiosqlite.Connection | None = None

    async def start(self, db: aiosqlite.Connection) -> None:
        self._db = db
        self._worker_task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

    async def execute[T](self, command: Callable[[aiosqlite.Connection], Awaitable[T]]) -> T:
        future: asyncio.Future[T] = asyncio.get_event_loop().create_future()
        await self._queue.put((command, future))
        return await future

    async def _run(self) -> None:
        assert self._db is not None
        while True:
            command, future = await self._queue.get()
            try:
                async with self._db.execute("BEGIN IMMEDIATE"):
                    result = await command(self._db)
                    await self._db.commit()
                future.set_result(result)
            except Exception as e:
                await self._db.rollback()
                future.set_exception(e)
            finally:
                self._queue.task_done()
