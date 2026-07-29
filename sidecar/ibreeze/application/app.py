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
    def __init__(
        self,
        *,
        socket_path: Path,
        profile_root: Path,
        app_version: str,
        startup_token: bytes,
        backend_origin: str,
        app_user_id: str,
        masked_identifier: str,
        device_id: str,
        profile_mode: str,
    ) -> None:
        database_path = profile_root / "profile.db"
        self._database_path = database_path
        self._socket_path = str(socket_path)
        self._app_version = app_version
        self._startup_token = startup_token
        self._backend_origin = backend_origin
        self._app_user_id = app_user_id
        self._masked_identifier = masked_identifier
        self._device_id = device_id
        self._profile_mode = profile_mode
        self._lifecycle: ApplicationLifecycle | None = None

    async def start(self) -> None:
        self._lifecycle = ApplicationLifecycle(self._database_path, socket_path=self._socket_path)
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
        return await self._lifecycle.health()

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
