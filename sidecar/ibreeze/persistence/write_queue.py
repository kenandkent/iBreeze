from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import UUID

import aiosqlite

_T = TypeVar("_T")

logger = logging.getLogger(__name__)


class WriteEnvelope[T]:
    def __init__(
        self,
        command_name: str,
        trace_id: UUID,
        deadline_at: datetime,
        execute: Callable[[aiosqlite.Connection], Awaitable[T]],
    ) -> None:
        self.command_name = command_name
        self.trace_id = trace_id
        self.deadline_at = deadline_at
        self.execute = execute
        self.future: asyncio.Future[T] = asyncio.get_event_loop().create_future()

    @property
    def result(self) -> Awaitable[T]:
        return self.future

    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.deadline_at


class WriteQueue:
    capacity: int = 32

    def __init__(self, connection: aiosqlite.Connection, capacity: int = 32) -> None:
        self.capacity = capacity
        self._queue: asyncio.Queue[WriteEnvelope[Any]] = asyncio.Queue(maxsize=capacity)
        self._connection = connection
        self._worker_task: asyncio.Task[None] | None = None
        self._running = True
        self._worker_task = asyncio.ensure_future(self._run())

    async def submit(
        self,
        command_name: str,
        trace_id: UUID,
        deadline_at: datetime,
        execute: Callable[[aiosqlite.Connection], Awaitable[_T]],
    ) -> _T:
        envelope = WriteEnvelope(
            command_name=command_name,
            trace_id=trace_id,
            deadline_at=deadline_at,
            execute=execute,
        )
        try:
            self._queue.put_nowait(envelope)
        except asyncio.QueueFull:
            raise RuntimeError("LOCAL_WRITE_BACKPRESSURE")
        return await envelope.result

    async def barrier(self, timeout: float = 10.0) -> None:
        async def _noop(_conn: aiosqlite.Connection) -> None:
            return None

        envelope = WriteEnvelope(
            command_name="__barrier__",
            trace_id=UUID(int=0),
            deadline_at=datetime.now(UTC).replace(year=9999),
            execute=_noop,
        )
        self._queue.put_nowait(envelope)
        try:
            await asyncio.wait_for(envelope.future, timeout=timeout)
        except TimeoutError:
            raise RuntimeError("BACKUP_WRITE_BARRIER_TIMEOUT")

    @property
    def depth(self) -> int:
        return self._queue.qsize()

    async def stop(self, timeout: float = 10.0) -> None:
        self._running = False
        if self._worker_task is not None:
            try:
                await asyncio.wait_for(self._queue.join(), timeout=timeout)
            except TimeoutError:
                pass
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

    async def _run(self) -> None:
        try:
            while True:
                try:
                    envelope = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except TimeoutError:
                    if not self._running:
                        break
                    continue
                if envelope.is_expired():
                    envelope.future.set_exception(RuntimeError("IPC_DEADLINE_EXCEEDED"))
                    self._queue.task_done()
                    continue
                try:
                    await self._connection.execute("BEGIN IMMEDIATE")
                    result = await envelope.execute(self._connection)
                    await self._connection.commit()
                    envelope.future.set_result(result)
                except Exception as e:
                    try:
                        await self._connection.rollback()
                    except Exception:
                        pass
                    envelope.future.set_exception(e)
                finally:
                    self._queue.task_done()
        except asyncio.CancelledError:
            pass
