from __future__ import annotations

import logging
from pathlib import Path

from ibreeze.application.lifecycle import ApplicationLifecycle, LifecyclePhase
from ibreeze.observability.health import HealthSnapshot
from ibreeze.persistence.connection import ReadPool
from ibreeze.persistence.unit_of_work import UnitOfWork
from ibreeze.persistence.write_queue import WriteQueue

logger = logging.getLogger(__name__)


class SidecarApplication:
    def __init__(self, profile_path: Path | None = None, profile_root: Path | None = None, **kwargs: object) -> None:
        self._profile_path = profile_path or profile_root or Path()
        raw_socket = kwargs.get("socket_path")
        self._socket_path: str | None = str(raw_socket) if raw_socket is not None else None
        self._lifecycle: ApplicationLifecycle | None = None

    async def start(self) -> None:
        self._lifecycle = ApplicationLifecycle(self._profile_path, socket_path=self._socket_path)
        await self._lifecycle.start()

    async def stop(self) -> None:
        if self._lifecycle is not None:
            await self._lifecycle.stop()

    async def health(self) -> HealthSnapshot:
        if self._lifecycle is None:
            return HealthSnapshot(
                status="unhealthy",
                observed_at="",
                event_loop_lag_ms=0,
                disk_free_bytes=0,
            )
        return self._lifecycle.health()

    @property
    def lifecycle(self) -> ApplicationLifecycle:
        assert self._lifecycle is not None
        return self._lifecycle

    @property
    def write_queue(self) -> WriteQueue:
        return self.lifecycle.write_queue

    @property
    def read_pool(self) -> ReadPool:
        return self.lifecycle.read_pool

    @property
    def unit_of_work(self) -> UnitOfWork:
        return self.lifecycle.unit_of_work

    @property
    def is_ready(self) -> bool:
        return self._lifecycle is not None and self._lifecycle.phase == LifecyclePhase.HANDSHAKE_READY
