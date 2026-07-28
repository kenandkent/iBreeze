import asyncio
import logging

from ibreeze.local_db import LocalDB
from ibreeze.persistence.write_queue import WriteQueue

logger = logging.getLogger(__name__)


class RuntimeWorker:
    def __init__(self, database: LocalDB, write_queue: WriteQueue) -> None:
        self._database = database
        self._write_queue = write_queue
        self._alive = False
        self._last_beat: float = 0.0
        self._task: asyncio.Task[None] | None = None

    @property
    def alive(self) -> bool:
        return self._alive

    @property
    def last_beat(self) -> float:
        return self._last_beat

    async def run(self) -> None:
        from ibreeze.runtime.run_executor import run_consumer_loop

        logger.info("RuntimeWorker started")
        self._alive = True
        db_path = self._database._db_path
        try:
            import aiosqlite
            async with aiosqlite.connect(db_path) as db:
                await db.execute("PRAGMA journal_mode=WAL")
                await db.execute("PRAGMA busy_timeout=5000")
                await run_consumer_loop(db, poll_interval=1.0, max_concurrent=4)
        except asyncio.CancelledError:
            logger.info("RuntimeWorker stopped")
        except Exception:
            logger.exception("RuntimeWorker crashed")
        finally:
            self._alive = False
