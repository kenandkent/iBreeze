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

        async def _dispatch_ready(conn: Any) -> int:
            now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            cursor = await conn.execute(
                """SELECT id, company_id, work_item_type, work_item_id,
                          job_id, run_id, priority
                   FROM runtime_queue
                   WHERE status='ready' AND priority >= 10
                   ORDER BY priority DESC, queued_at ASC
                   LIMIT 10"""
            )
            rows = await cursor.fetchall()
            if not rows:
                return 0
            for row in rows:
                await conn.execute(
                    """UPDATE runtime_queue
                       SET status='leased', leased_at=?
                       WHERE id=? AND status='ready'""",
                    (now, row["id"]),
                )
            return len(rows)

        try:
            deadline = datetime.now(UTC) + timedelta(seconds=25)
            count = await wq.submit("runtime.dispatch_ready", UUID(int=0), deadline, _dispatch_ready)
            if count:
                logger.info("RuntimeWorker dispatched %d ready items", count)
        except Exception:
            logger.exception("RuntimeWorker dispatch failed")
