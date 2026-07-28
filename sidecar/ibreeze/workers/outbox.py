from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from ibreeze.events.outbox import OutboxWriter
from ibreeze.persistence.write_queue import WriteQueue
from ibreeze.workers.spec import BaseWorker

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50


class OutboxWorker(BaseWorker):
    name = "OutboxWorker"

    def __init__(self, write_queue: WriteQueue | None = None) -> None:
        super().__init__()
        self._write_queue = write_queue
        self._outbox = OutboxWriter()

    async def work(self) -> None:
        wq = self._write_queue
        if wq is None:
            await asyncio.sleep(1)
            return

        async def _deliver(conn: Any) -> int:
            cursor = await conn.execute(
                """SELECT id, topic, payload_json, domain_event_id, attempts
                   FROM outbox
                   WHERE status = 'pending' AND next_attempt_at <= ?
                   ORDER BY created_at ASC
                   LIMIT ?""",
                (datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), _BATCH_SIZE),
            )
            rows = await cursor.fetchall()
            if not rows:
                return 0
            for row in rows:
                await conn.execute(
                    """UPDATE outbox
                       SET status = 'delivered', delivered_at = ?, attempts = attempts + 1
                       WHERE id = ?""",
                    (datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), row["id"]),
                )
            await conn.commit()
            return len(rows)

        try:
            deadline = datetime.now(UTC) + timedelta(seconds=30)
            delivered = await wq.submit("outbox.deliver", UUID(int=0), deadline, _deliver)
            if delivered:
                logger.info("OutboxWorker delivered %d events", delivered)
        except Exception:
            logger.exception("OutboxWorker deliver failed")
