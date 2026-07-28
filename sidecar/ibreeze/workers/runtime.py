from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from ibreeze.persistence.write_queue import WriteQueue
from ibreeze.workers.spec import BaseWorker

logger = logging.getLogger(__name__)


class RuntimeWorker(BaseWorker):
    name = "RuntimeWorker"

    def __init__(self, write_queue: WriteQueue | None = None) -> None:
        super().__init__()
        self._write_queue = write_queue

    async def work(self) -> None:
        wq = self._write_queue
        if wq is None:
            await asyncio.sleep(1)
            return

        async def _tick(conn: object) -> None:
            pass

        try:
            await wq.submit("runtime.tick", UUID(int=0), datetime.now(UTC) + timedelta(seconds=30), _tick)
        except Exception:
            logger.exception("RuntimeWorker tick failed")
