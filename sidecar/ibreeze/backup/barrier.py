from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import aiosqlite

from ibreeze.persistence.write_queue import WriteQueue


@asynccontextmanager
async def acquire_backup_barrier(
    writer: aiosqlite.Connection,
    write_queue: WriteQueue,
    timeout: timedelta | None = None,
) -> AsyncIterator[None]:
    if timeout is None:
        timeout = timedelta(seconds=30)
    try:
        await asyncio.wait_for(
            write_queue.barrier(timeout=timeout.total_seconds()),
            timeout=timeout.total_seconds(),
        )
    except (TimeoutError, RuntimeError):
        raise RuntimeError("BACKUP_WRITE_BARRIER_TIMEOUT")
    try:
        await writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        yield
    finally:
        pass
