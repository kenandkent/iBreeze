import asyncio
import logging

logger = logging.getLogger(__name__)


class OutboxWorker:
    def __init__(self, database: object, write_queue: object) -> None:
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
        logger.info("OutboxWorker started")
        self._alive = True
        try:
            while True:
                await asyncio.sleep(5)
                self._last_beat = asyncio.get_event_loop().time()
        except asyncio.CancelledError:
            logger.info("OutboxWorker stopped")
        except Exception:
            logger.exception("OutboxWorker crashed")
        finally:
            self._alive = False
