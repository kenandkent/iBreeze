import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from ibreeze.local_db import LocalDB
from ibreeze.persistence.write_queue import WriteQueue

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class AnalysisWorker:
    def __init__(self, database: LocalDB, write_queue: WriteQueue) -> None:
        self._database = database
        self._write_queue = write_queue
        self._alive = False
        self._last_beat: float = 0.0

    @property
    def alive(self) -> bool:
        return self._alive

    @property
    def last_beat(self) -> float:
        return self._last_beat

    async def run(self) -> None:
        logger.info("AnalysisWorker started")
        self._alive = True
        try:
            while True:
                await self._cleanup_expired_leases()
                self._last_beat = time.time()
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("AnalysisWorker stopped")
        finally:
            self._alive = False

    async def _cleanup_expired_leases(self) -> None:
        now = _now()

        async def _do_cleanup(db: Any) -> int:
            expired = await (await db.execute(
                """SELECT id, queue_id, job_id, run_id, company_id
                   FROM runtime_leases WHERE expires_at < ?""",
                (now,),
            )).fetchall()
            if not expired:
                return 0
            for row in expired:
                await db.execute(
                    """UPDATE runtime_queue
                       SET status='ready'
                       WHERE id=? AND status='leased'""",
                    (row["queue_id"],),
                )
                await db.execute(
                    "DELETE FROM runtime_leases WHERE id=?",
                    (row["id"],),
                )
                if row["run_id"]:
                    await db.execute(
                        """UPDATE agent_runs
                           SET status='lost', updated_at=?, version=version+1
                           WHERE id=? AND company_id=?""",
                        (now, row["run_id"], row["company_id"]),
                    )
            return len(expired)

        try:
            count = await self._write_queue.execute(_do_cleanup)
            if count:
                logger.info("Cleaned up %d expired runtime leases", count)
        except Exception:
            logger.exception("Failed to cleanup expired leases")
