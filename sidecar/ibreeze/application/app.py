from __future__ import annotations

import logging
from pathlib import Path

from ibreeze.application.lifecycle import ApplicationLifecycle, LifecyclePhase
from ibreeze.observability.health import HealthSnapshot
from ibreeze.persistence.connection import ReadPool
from ibreeze.persistence.unit_of_work import UnitOfWork
from ibreeze.persistence.write_queue import WriteQueue
from ibreeze.rpc.production_server import ProductionRpcServer

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
        launch_id: str = "",
    ) -> None:
        database_path = profile_root / "profile.db"
        self._database_path = database_path
        self._socket_path = str(socket_path)
        self._app_version = app_version
        self._launch_id = launch_id
        self._startup_token = startup_token
        self._backend_origin = backend_origin
        self._app_user_id = app_user_id
        self._masked_identifier = masked_identifier
        self._device_id = device_id
        self._profile_mode = profile_mode
        self._lifecycle: ApplicationLifecycle | None = None
        self._rpc_server: ProductionRpcServer | None = None

    async def start(self) -> None:
        lifecycle_kwargs = {
            "socket_path": self._socket_path,
            "backend_origin": self._backend_origin,
            "app_user_id": self._app_user_id,
            "masked_identifier": self._masked_identifier,
            "device_id": self._device_id,
            "app_version": self._app_version,
            "profile_mode": self._profile_mode,
        }
        # Older embedded launchers did not pass a launch id; keep that
        # constructor shape compatible while production Rust always does.
        if self._launch_id:
            lifecycle_kwargs["launch_id"] = self._launch_id
        self._lifecycle = ApplicationLifecycle(self._database_path, **lifecycle_kwargs)
        await self._lifecycle.start()
        self._rpc_server = ProductionRpcServer(
            lifecycle=self._lifecycle,
            socket_path=Path(self._socket_path),
            startup_token=self._startup_token,
            app_version=self._app_version,
            launch_id=self._launch_id,
        )
        await self._rpc_server.start()

    async def stop(self) -> None:
        if self._rpc_server is not None:
            await self._rpc_server.stop()
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
    def rpc_server(self) -> ProductionRpcServer:
        assert self._rpc_server is not None
        return self._rpc_server

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
