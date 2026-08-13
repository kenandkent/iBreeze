from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from ibreeze.persistence.connection import ReadPool
from ibreeze.persistence.write_queue import WriteQueue
from ibreeze.runtime.run_executor import RuntimeExecutionService
from ibreeze.workers.spec import BaseWorker

logger = logging.getLogger(__name__)


class RuntimeWorker(BaseWorker):
    """Claim, execute and complete AgentRuns through the canonical runtime service."""

    name = "RuntimeWorker"

    def __init__(
        self,
        write_queue: WriteQueue | None = None,
        read_pool: ReadPool | None = None,
        command_bus: object | None = None,
    ) -> None:
        super().__init__(write_queue=write_queue)
        self._read_pool = read_pool
        self._executor = (
            RuntimeExecutionService(read_pool, write_queue, command_bus) if read_pool is not None and write_queue is not None else None
        )

    async def work(self) -> None:
        if self._executor is None:
            # A worker without both dependencies is not executable.  Keep a
            # read-only diagnostic transaction for isolated fixtures; the
            # production lifecycle always supplies both dependencies.
            if self._write_queue is not None:

                async def inspect_ready(conn: Any) -> int:
                    cursor = await conn.execute("SELECT id FROM runtime_queue WHERE status='ready' LIMIT 10")
                    rows = await cursor.fetchall()
                    return len(rows)

                try:
                    await self._write_queue.submit(
                        "runtime.dispatch_ready",
                        UUID(int=0),
                        datetime.now(UTC) + timedelta(seconds=25),
                        inspect_ready,
                    )
                except Exception:
                    logger.exception("RuntimeWorker dispatch failed")
            else:
                await asyncio.sleep(1)
            return
        try:
            count = await self._executor.work(self.update_heartbeat)
            if count:
                logger.info("RuntimeWorker executed %d run", count)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("RuntimeWorker execution failed")
