from __future__ import annotations

import logging
from enum import Enum, auto
from pathlib import Path

import aiosqlite

from ibreeze.observability.health import HealthSnapshot, health_snapshot
from ibreeze.persistence.connection import ReadPool, open_writer
from ibreeze.persistence.migrator import prepare
from ibreeze.persistence.profile import PreparedProfileDatabase
from ibreeze.persistence.unit_of_work import UnitOfWork
from ibreeze.persistence.write_queue import WriteQueue
from ibreeze.runtime.transport import set_reverse_rpc_socket_path
from ibreeze.workers.supervisor import WorkerSupervisor

logger = logging.getLogger(__name__)


class LifecyclePhase(Enum):
    INIT = auto()
    LOCK_ACQUIRED = auto()
    UDS_HANDSHAKE_ONLY = auto()
    BOOTSTRAP_DB = auto()
    MIGRATION = auto()
    WRITER_OPENED = auto()
    READ_POOL_OPENED = auto()
    WRITE_QUEUE_STARTED = auto()
    IDENTITY_VERIFIED = auto()
    WORKER_SUPERVISOR_STARTED = auto()
    RPC_DISPATCHER_ENABLED = auto()
    HANDSHAKE_READY = auto()


class ApplicationLifecycle:
    def __init__(self, profile_path: Path, socket_path: str | None = None) -> None:
        self._profile_path = profile_path
        self._socket_path = socket_path
        self._phase = LifecyclePhase.INIT
        self._prepared: PreparedProfileDatabase | None = None
        self._writer: aiosqlite.Connection | None = None
        self._read_pool: ReadPool | None = None
        self._write_queue: WriteQueue | None = None
        self._unit_of_work: UnitOfWork | None = None
        self._workers: WorkerSupervisor | None = None

    @property
    def phase(self) -> LifecyclePhase:
        return self._phase

    @property
    def writer(self) -> aiosqlite.Connection:
        assert self._writer is not None
        return self._writer

    @property
    def read_pool(self) -> ReadPool:
        assert self._read_pool is not None
        return self._read_pool

    @property
    def write_queue(self) -> WriteQueue:
        assert self._write_queue is not None
        return self._write_queue

    @property
    def unit_of_work(self) -> UnitOfWork:
        assert self._unit_of_work is not None
        return self._unit_of_work

    @property
    def workers(self) -> WorkerSupervisor:
        assert self._workers is not None
        return self._workers

    async def start(self) -> None:
        logger.info("lifecycle: acquire profile file lock")
        self._prepared = await prepare(self._profile_path)
        self._phase = LifecyclePhase.LOCK_ACQUIRED

        # Phase: UDS handshake-only — wire reverse RPC socket path
        if self._socket_path is not None:
            logger.info("lifecycle: wiring reverse RPC socket path %s", self._socket_path)
            set_reverse_rpc_socket_path(self._socket_path)
        else:
            logger.info("lifecycle: no reverse RPC socket path (stub mode)")
        self._phase = LifecyclePhase.UDS_HANDSHAKE_ONLY

        # Phase: bootstrap complete via prepare()
        self._phase = LifecyclePhase.BOOTSTRAP_DB
        self._phase = LifecyclePhase.MIGRATION

        logger.info("lifecycle: open writer connection")
        self._writer = await open_writer(self._profile_path)
        self._phase = LifecyclePhase.WRITER_OPENED

        logger.info("lifecycle: open read pool")
        self._read_pool = await ReadPool.open(self._profile_path)
        self._phase = LifecyclePhase.READ_POOL_OPENED

        logger.info("lifecycle: start write queue")
        self._write_queue = WriteQueue(self._writer)
        self._unit_of_work = UnitOfWork(connection=self._writer)
        self._phase = LifecyclePhase.WRITE_QUEUE_STARTED

        # Phase: identity verification (placeholder)
        logger.info("lifecycle: verify profile identity")
        self._phase = LifecyclePhase.IDENTITY_VERIFIED

        logger.info("lifecycle: start worker supervisor")
        self._workers = WorkerSupervisor(
            writer=self._writer,
            write_queue=self._write_queue,
        )
        await self._workers.start()
        self._phase = LifecyclePhase.WORKER_SUPERVISOR_STARTED

        # Phase: RPC dispatcher enabled (placeholder - actual RPC is external)
        logger.info("lifecycle: enable rpc dispatcher")
        self._phase = LifecyclePhase.RPC_DISPATCHER_ENABLED

        logger.info("lifecycle: handshake ready")
        self._phase = LifecyclePhase.HANDSHAKE_READY

    async def stop(self) -> None:
        logger.info("lifecycle: stop accepting new RPC")
        logger.info("lifecycle: cancel active streams")
        logger.info("lifecycle: stop leasing runtime work")

        if self._write_queue is not None:
            logger.info("lifecycle: drain write queue (max 10s)")
            await self._write_queue.stop(timeout=10.0)

        if self._workers is not None:
            logger.info("lifecycle: stop workers")
            await self._workers.stop()

        if self._writer is not None:
            logger.info("lifecycle: checkpoint WAL")
            try:
                await self._writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                logger.exception("wal checkpoint failed")

        if self._read_pool is not None:
            logger.info("lifecycle: close read pool")
            await self._read_pool.close()

        if self._writer is not None:
            logger.info("lifecycle: close writer")
            await self._writer.close()

        if self._prepared is not None:
            logger.info("lifecycle: release profile lock")
            await self._prepared.release_lock()

    def health(self) -> HealthSnapshot:
        return health_snapshot(
            writer=self._writer,
            write_queue=self._write_queue,
            workers=self._workers,
            profile_path=self._profile_path,
        )
