import asyncio
import logging

from ibreeze.local_db import LocalDB
from ibreeze.persistence.write_queue import WriteQueue
from ibreeze.runtime.run_executor import run_consumer_loop

logger = logging.getLogger(__name__)


class RuntimeWorker:
    def __init__(self, database: LocalDB, write_queue: WriteQueue) -> None:
        self._database = database
        self._write_queue = write_queue

    async def run(self) -> None:
        logger.info("RuntimeWorker started")
        db = self._database._write_conn
        try:
            await run_consumer_loop(db, poll_interval=1.0, max_concurrent=4)
        except asyncio.CancelledError:
            logger.info("RuntimeWorker stopped")
