import asyncio
import logging

from ibreeze.local_db import LocalDB
from ibreeze.persistence.write_queue import WriteQueue

logger = logging.getLogger(__name__)


class RuntimeWorker:
    def __init__(self, database: LocalDB, write_queue: WriteQueue) -> None:
        self._database = database
        self._write_queue = write_queue

    async def run(self) -> None:
        logger.info("RuntimeWorker started")
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("RuntimeWorker stopped")
