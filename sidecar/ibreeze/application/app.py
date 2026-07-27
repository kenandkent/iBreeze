import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from ibreeze.local_db import LocalDB
from ibreeze.persistence.migrations import run_migrations
from ibreeze.persistence.read_pool import ReadPool
from ibreeze.persistence.write_queue import WriteQueue
from ibreeze.rpc_server import RPCServer
from ibreeze.workers.analysis import AnalysisWorker
from ibreeze.workers.runtime import RuntimeWorker

logger = logging.getLogger(__name__)


@dataclass
class HealthSnapshot:
    status: str = "unknown"
    database_status: str = "unknown"
    worker_count: int = 0
    healthy_workers: int = 0
    analysis_worker_alive: bool = False
    runtime_worker_alive: bool = False
    analysis_worker_last_beat: float = 0.0
    runtime_worker_last_beat: float = 0.0
    errors: list[str] = field(default_factory=list)


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
        self._socket_path = socket_path
        self._profile_root = profile_root
        self._app_version = app_version
        self._startup_token = startup_token
        self._backend_origin = backend_origin
        self._app_user_id = app_user_id
        self._masked_identifier = masked_identifier
        self._device_id = device_id
        self._profile_mode = profile_mode

        self._database: LocalDB | None = None
        self._write_queue = WriteQueue(capacity=32)
        self._read_pool = ReadPool(size=8)
        self._server: RPCServer | None = None
        self._workers: list[asyncio.Task[None]] = []
        self._worker_instances: list = []
        self._health = HealthSnapshot()
        self._monitor_task: asyncio.Task | None = None

    async def start(self) -> None:
        db_path = self._profile_root / "profile.db"

        # Initialize database
        self._database = LocalDB(db_path)
        await self._database.initialize()

        db_conn = self._database._write_conn
        assert db_conn is not None

        # Run migrations
        await run_migrations(db_conn)
        self._health.database_status = "ready"

        # Initialize profile
        await self._database.initialize_profile(
            profile_id=self._profile_root.name,
            backend_origin=self._backend_origin,
            app_user_id=self._app_user_id,
            masked_identifier=self._masked_identifier,
            device_id=self._device_id,
            allow_create=self._profile_mode == "online",
        )

        # Start write queue and read pool
        await self._write_queue.start(db_conn)
        await self._read_pool.start(str(db_path))

        # Start RPC server
        self._server = RPCServer(
            self._database,
            self._socket_path,
            startup_token=self._startup_token,
            launch_id=self._socket_path.parent.name,
            app_version=self._app_version,
            write_queue=self._write_queue,
        )

        # Start background workers
        analysis = AnalysisWorker(self._database, self._write_queue)
        runtime = RuntimeWorker(self._database, self._write_queue)
        self._worker_instances = [analysis, runtime]
        self._workers = [
            asyncio.create_task(analysis.run()),
            asyncio.create_task(runtime.run()),
        ]
        self._health.status = "healthy"
        self._health.worker_count = len(self._workers)
        self._health.healthy_workers = len(self._workers)

        # Start health monitor
        self._monitor_task = asyncio.create_task(self._monitor_health())

        # Serve RPC (blocks until shutdown)
        try:
            await self._server.serve_forever()
        finally:
            await self.stop()

    async def _monitor_health(self) -> None:
        """Periodically check worker health and update snapshot."""
        while True:
            await asyncio.sleep(30)
            try:
                alive_count = 0
                for inst in self._worker_instances:
                    if inst.alive:
                        alive_count += 1
                self._health.healthy_workers = alive_count
                if alive_count < self._health.worker_count:
                    self._health.status = "degraded"
                else:
                    self._health.status = "healthy"
            except Exception:
                logger.exception("Health monitor check failed")

    async def stop(self, grace_seconds: float = 10.0) -> None:
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        for w in self._workers:
            w.cancel()
        if self._workers:
            await asyncio.wait(self._workers, timeout=grace_seconds)
        await self._write_queue.stop()
        await self._read_pool.stop()
        if self._server:
            await self._server.close()
        if self._database:
            await self._database.close()

    async def health(self) -> HealthSnapshot:
        if self._worker_instances:
            analysis = self._worker_instances[0]
            runtime = self._worker_instances[1]
            self._health.analysis_worker_alive = analysis.alive
            self._health.runtime_worker_alive = runtime.alive
            self._health.analysis_worker_last_beat = analysis.last_beat
            self._health.runtime_worker_last_beat = runtime.last_beat
        return self._health
