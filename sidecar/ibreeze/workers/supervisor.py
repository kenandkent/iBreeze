from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import aiosqlite

from ibreeze.application.command_bus import InternalCommandBus
from ibreeze.persistence.connection import ReadPool
from ibreeze.persistence.write_queue import WriteQueue
from ibreeze.workers.analysis import AnalysisWorker
from ibreeze.workers.outbox import OutboxWorker
from ibreeze.workers.runtime import RuntimeWorker
from ibreeze.workers.spec import (
    BackupWorker,
    BaseWorker,
    EventCompactionWorker,
    KnowledgeWorker,
    ReconciliationWorker,
    WorkerHealth,
)

logger = logging.getLogger(__name__)


class WorkerSupervisor:
    BACKOFF_SECONDS = [1, 2, 4, 8, 16]
    MAX_RESTARTS_IN_5MIN = 5
    HEARTBEAT_INTERVAL = 5
    HEARTBEAT_TIMEOUT = 15

    def __init__(
        self,
        writer: aiosqlite.Connection,
        write_queue: WriteQueue,
        read_pool: ReadPool | None = None,
        command_bus: InternalCommandBus | None = None,
    ) -> None:
        self._writer = writer
        self._write_queue = write_queue
        self._read_pool = read_pool
        self._command_bus = command_bus
        self._workers: list[WorkerEntry] = []
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        worker_defs: list[type[BaseWorker]] = [
            RuntimeWorker,
            AnalysisWorker,
            OutboxWorker,
            KnowledgeWorker,
            ReconciliationWorker,
            BackupWorker,
            EventCompactionWorker,
        ]
        for cls in worker_defs:
            worker: BaseWorker
            if cls is OutboxWorker:
                worker = cls(write_queue=self._write_queue, command_bus=self._command_bus)
            elif cls is RuntimeWorker:
                worker = cls(
                    write_queue=self._write_queue,
                    read_pool=self._read_pool,
                    command_bus=self._command_bus,
                )
            else:
                worker = cls(write_queue=self._write_queue)
            entry = WorkerEntry(worker=worker)
            self._workers.append(entry)
            task = asyncio.create_task(self._run_worker(entry))
            self._tasks.append(task)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    def health(self) -> list[WorkerHealth]:
        now = datetime.now(UTC)
        result: list[WorkerHealth] = []
        for entry in self._workers:
            wh = entry.worker.health()
            hb_str = wh.heartbeat_at
            if hb_str:
                try:
                    hb_time = datetime.fromisoformat(hb_str.replace("Z", "+00:00"))
                    if (now - hb_time).total_seconds() > self.HEARTBEAT_TIMEOUT:
                        wh.state = "failed"
                except ValueError:
                    wh.state = "failed"
            result.append(wh)
        return result

    async def _run_worker(self, entry: WorkerEntry) -> None:
        restart_times: list[float] = []
        while True:
            worker = entry.worker
            worker._state = "starting"
            try:
                await asyncio.sleep(0)
                while True:
                    worker.update_heartbeat()
                    worker._state = "healthy"
                    await worker.work()
                    worker.mark_success()
                    # Workers are polling loops.  Keep an idle worker from
                    # spinning the event loop and continuously enqueuing
                    # empty write transactions.
                    await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                worker._state = "stopped"
                return
            except Exception as exc:
                logger.warning("worker %s failed: %s", worker.name, exc)
                worker.mark_error(str(exc)[:100])
                worker._state = "failed"
                now = asyncio.get_event_loop().time()
                restart_times.append(now)
                cutoff = now - 300
                restart_times = [t for t in restart_times if t > cutoff]
                if len(restart_times) > self.MAX_RESTARTS_IN_5MIN:
                    logger.error("worker %s exceeded max restarts", worker.name)
                    worker._state = "failed"
                    while True:
                        try:
                            await asyncio.sleep(60)
                        except asyncio.CancelledError:
                            worker._state = "stopped"
                            return
                backoff_index = min(len(restart_times) - 1, len(self.BACKOFF_SECONDS) - 1)
                delay = self.BACKOFF_SECONDS[backoff_index]
                logger.info("worker %s restarting in %ds", worker.name, delay)
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    worker._state = "stopped"
                    return


class WorkerEntry:
    def __init__(self, worker: BaseWorker) -> None:
        self.worker = worker
