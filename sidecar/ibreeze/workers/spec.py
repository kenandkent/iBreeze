from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class WorkerHealth:
    name: str
    state: str = "stopped"
    heartbeat_at: str = ""
    last_success_at: str | None = None
    last_error_code: str | None = None
    queue_lag: int = 0
    restart_count: int = 0


class BaseWorker:
    name: str = "base"

    def __init__(self) -> None:
        self._state = "stopped"
        self._heartbeat_at = ""
        self._last_success_at: str | None = None
        self._last_error_code: str | None = None
        self._restart_count = 0

    async def work(self) -> None:
        raise NotImplementedError

    def health(self) -> WorkerHealth:
        return WorkerHealth(
            name=self.name,
            state=self._state,
            heartbeat_at=self._heartbeat_at,
            last_success_at=self._last_success_at,
            last_error_code=self._last_error_code,
            restart_count=self._restart_count,
        )

    def update_heartbeat(self) -> None:
        self._heartbeat_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def mark_success(self) -> None:
        self._last_success_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def mark_error(self, code: str) -> None:
        self._last_error_code = code


class KnowledgeWorker(BaseWorker):
    name = "KnowledgeWorker"

    async def work(self) -> None:
        import asyncio
        await asyncio.sleep(30)


class ReconciliationWorker(BaseWorker):
    name = "ReconciliationWorker"

    async def work(self) -> None:
        import asyncio
        await asyncio.sleep(60)


class BackupWorker(BaseWorker):
    name = "BackupWorker"

    async def work(self) -> None:
        import asyncio
        await asyncio.sleep(3600)


class EventCompactionWorker(BaseWorker):
    name = "EventCompactionWorker"

    async def work(self) -> None:
        import asyncio
        await asyncio.sleep(3600)

