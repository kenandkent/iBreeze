import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from ibreeze.local_db import LocalDB
from ibreeze.persistence.migrations import run_migrations
from ibreeze.persistence.read_pool import ReadPool
from ibreeze.persistence.write_queue import WriteQueue
from ibreeze.rpc_server import RPCServer
from ibreeze.workers.analysis import AnalysisWorker
from ibreeze.workers.runtime import RuntimeWorker


@dataclass
class HealthSnapshot:
    status: str = "unknown"
    database_status: str = "unknown"
    worker_count: int = 0
    healthy_workers: int = 0
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
        self._health = HealthSnapshot()

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
        self._workers = [
            asyncio.create_task(AnalysisWorker(self._database, self._write_queue).run()),
            asyncio.create_task(RuntimeWorker(self._database, self._write_queue).run()),
        ]
        self._health.status = "healthy"
        self._health.worker_count = len(self._workers)
        self._health.healthy_workers = len(self._workers)

        # Serve RPC (blocks until shutdown)
        try:
            await self._server.serve_forever()
        finally:
            await self.stop()

    async def stop(self, grace_seconds: float = 10.0) -> None:
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
        return self._health
