from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from ibreeze.persistence.write_queue import WriteQueue
from ibreeze.workers.spec import BaseWorker

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class AnalysisWorker(BaseWorker):
    name = "AnalysisWorker"

    def __init__(self, write_queue: WriteQueue | None = None) -> None:
        super().__init__()
        self._write_queue = write_queue

    async def work(self) -> None:
        wq = self._write_queue
        if wq is None:
            await asyncio.sleep(1)
            return

        async def _cleanup(conn: Any) -> int:
            now = _now()
            expired = await (await conn.execute(
                """SELECT id, queue_id, job_id, run_id, company_id
                   FROM runtime_leases WHERE expires_at < ?""",
                (now,),
            )).fetchall()
            if not expired:
                return 0
            for row in expired:
                await conn.execute(
                    """UPDATE runtime_queue
                       SET status='ready'
                       WHERE id=? AND status='leased'""",
                    (row["queue_id"],),
                )
                await conn.execute(
                    "DELETE FROM runtime_leases WHERE id=?",
                    (row["id"],),
                )
                if row["run_id"]:
                    await conn.execute(
                        """UPDATE agent_runs
                           SET status='lost', updated_at=?, version=version+1
                           WHERE id=? AND company_id=?""",
                        (now, row["run_id"], row["company_id"]),
                    )
            return len(expired)

        try:
            deadline = datetime.now(UTC) + timedelta(seconds=295)
            count = await wq.submit("analysis.cleanup_leases", UUID(int=0), deadline, _cleanup)
            if count:
                logger.info("Cleaned up %d expired runtime leases", count)
        except Exception:
            logger.exception("AnalysisWorker cleanup failed")
