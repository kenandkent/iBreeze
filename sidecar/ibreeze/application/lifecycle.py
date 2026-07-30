from __future__ import annotations

import asyncio
import dataclasses
import logging
from datetime import UTC, datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any
from uuid import UUID

import aiosqlite

from ibreeze.application.completion_handlers import (
    AcceptEmployeeTaskHandler,
    CompanyGate,
    CompleteCompanyTaskHandler,
    CompleteDepartmentTaskHandler,
    DepartmentGate,
    EmployeeGate,
)
from ibreeze.application.review_handlers import (
    CloseIssueHandler,
    RejectIssueHandler,
    ResolveIssueHandler,
    StartIssueFixHandler,
    StartReviewHandler,
    SubmitReviewGuards,
    SubmitReviewHandler,
    VerifyIssueHandler,
)
from ibreeze.domain.review.commands import (
    CloseIssue,
    RejectIssue,
    ResolveIssue,
    ReviewIssueInput,
    StartIssueFix,
    StartReview,
    SubmitReview,
    VerifyIssue,
)
from ibreeze.domain.review.repository import ReviewRepository
from ibreeze.domain.tasks.commands import (
    AcceptEmployeeTask,
    CompleteCompanyTask,
    CompleteDepartmentTask,
)
from ibreeze.observability.health import HealthSnapshot, health_snapshot_async, tick_heartbeat
from ibreeze.persistence.connection import ReadPool, open_writer
from ibreeze.persistence.migrator import prepare
from ibreeze.persistence.profile import PreparedProfileDatabase
from ibreeze.persistence.unit_of_work import UnitOfWork
from ibreeze.persistence.write_queue import WriteQueue
from ibreeze.rpc.dispatcher import Dispatcher, ReverseMethodTable
from ibreeze.rpc.handler_registry import register_legacy_handlers
from ibreeze.runtime.transport import mark_sidecar_own_socket, set_reverse_rpc_socket_path
from ibreeze.workers.supervisor import WorkerSupervisor

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _dict_to_uuid(v: Any) -> UUID:
    return UUID(v) if isinstance(v, str) else v


def _build_command(command_cls: type, params: dict[str, Any]) -> Any:
    kwargs: dict[str, Any] = {}
    for f in dataclasses.fields(command_cls):
        val = params.get(f.name)
        if val is None:
            continue
        if f.type is UUID:
            kwargs[f.name] = _dict_to_uuid(val)
        elif f.type == tuple[ReviewIssueInput, ...]:
            kwargs[f.name] = tuple(
                ReviewIssueInput(
                    client_issue_id=_dict_to_uuid(i["client_issue_id"]),
                    severity=i["severity"],
                    category=i["category"],
                    description=i["description"],
                    expected=i["expected"],
                    actual=i["actual"],
                    evidence_refs=tuple(_dict_to_uuid(e) for e in i.get("evidence_refs", [])),
                    suggested_fix=i["suggested_fix"],
                    assignee_employee_id=_dict_to_uuid(i["assignee_employee_id"])
                    if i.get("assignee_employee_id") else None,
                )
                for i in val
            )
        else:
            kwargs[f.name] = val
    return command_cls(**kwargs)


def _handler(handler: Any, command_cls: type) -> Any:
    async def wrapped(params: dict[str, Any], session: object) -> Any:
        idempotency_key = params.get("idempotency_key")
        command = _build_command(command_cls, params)
        return await handler.handle(idempotency_key, command)
    return wrapped


def _submit_handler(handler: SubmitReviewHandler) -> Any:
    async def wrapped(params: dict[str, Any], session: object) -> Any:
        idempotency_key = params.get("idempotency_key")
        command = _build_command(SubmitReview, params)
        return await handler.handle(idempotency_key, command)
    return wrapped


class ApplicationLifecycle:
    def __init__(
        self,
        profile_path: Path,
        socket_path: str | None = None,
        *,
        backend_origin: str = "",
        app_user_id: str = "",
        masked_identifier: str = "",
        device_id: str = "",
        profile_mode: str = "offline",
    ) -> None:
        self._profile_path = profile_path
        self._socket_path = socket_path
        self._backend_origin = backend_origin
        self._app_user_id = app_user_id
        self._masked_identifier = masked_identifier
        self._device_id = device_id
        self._profile_mode = profile_mode
        self._phase = LifecyclePhase.INIT
        self._prepared: PreparedProfileDatabase | None = None
        self._writer: aiosqlite.Connection | None = None
        self._read_pool: ReadPool | None = None
        self._write_queue: WriteQueue | None = None
        self._unit_of_work: UnitOfWork | None = None
        self._workers: WorkerSupervisor | None = None
        self._dispatcher: Dispatcher = Dispatcher()
        self._reverse_table: ReverseMethodTable = ReverseMethodTable()
        self._heartbeat_task: asyncio.Task[None] | None = None

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

    @property
    def dispatcher(self) -> Dispatcher:
        return self._dispatcher

    @property
    def reverse_table(self) -> ReverseMethodTable:
        return self._reverse_table

    async def start(self) -> None:
        logger.info("lifecycle: acquire profile file lock")
        self._prepared = await prepare(self._profile_path)
        self._phase = LifecyclePhase.LOCK_ACQUIRED

        # Start independent heartbeat task (ticks every 5 s so event-loop lag is measurable)
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Phase: UDS handshake-only — wire reverse RPC socket path
        if self._socket_path is not None:
            logger.info("lifecycle: wiring reverse RPC socket path %s", self._socket_path)
            set_reverse_rpc_socket_path(self._socket_path)
            mark_sidecar_own_socket(self._socket_path)
        else:
            logger.info("lifecycle: no reverse RPC socket path (stub mode)")
        self._phase = LifecyclePhase.UDS_HANDSHAKE_ONLY

        logger.info("lifecycle: bootstrap and migrate database")
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

        logger.info("lifecycle: verify profile identity")
        await self._ensure_profile_identity()
        self._phase = LifecyclePhase.IDENTITY_VERIFIED

        logger.info("lifecycle: start worker supervisor")
        self._workers = WorkerSupervisor(
            writer=self._writer,
            write_queue=self._write_queue,
        )
        await self._workers.start()
        self._phase = LifecyclePhase.WORKER_SUPERVISOR_STARTED

        logger.info("lifecycle: enable rpc dispatcher")
        self._phase = LifecyclePhase.RPC_DISPATCHER_ENABLED

        logger.info("lifecycle: register core system handlers")
        self._dispatcher.register("system.health", self._handle_system_health)
        self._dispatcher.register("system.shutdown", self._handle_system_shutdown)

        logger.info("lifecycle: register review/completion handlers")
        await self._init_review_completion_handlers()

        logger.info("lifecycle: register legacy RPC handlers")
        count = register_legacy_handlers(
            self._dispatcher,
            self._writer,
            self._profile_path,
            write_queue=self._write_queue,
        )
        logger.info("lifecycle: registered %d legacy handlers", count)

        logger.info("lifecycle: handshake ready")
        self._phase = LifecyclePhase.HANDSHAKE_READY

    async def stop(self) -> None:
        logger.info("lifecycle: stop accepting new RPC")
        logger.info("lifecycle: cancel active streams")
        logger.info("lifecycle: stop leasing runtime work")

        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

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

    async def _init_review_completion_handlers(self) -> None:
        repo = ReviewRepository()
        uow = self._unit_of_work

        self._dispatcher.register("review.start", _handler(StartReviewHandler(repo, uow), StartReview))
        self._dispatcher.register("review.startIssueFix", _handler(StartIssueFixHandler(repo, uow), StartIssueFix))
        self._dispatcher.register("review.resolveIssue", _handler(ResolveIssueHandler(repo, uow), ResolveIssue))
        guard = SubmitReviewGuards(repo)
        self._dispatcher.register("review.submit", _submit_handler(SubmitReviewHandler(repo, guard, uow)))
        self._dispatcher.register("review.verifyIssue", _handler(VerifyIssueHandler(repo, uow), VerifyIssue))
        self._dispatcher.register("review.closeIssue", _handler(CloseIssueHandler(repo, uow), CloseIssue))
        self._dispatcher.register("review.rejectIssue", _handler(RejectIssueHandler(repo, uow), RejectIssue))

        self._dispatcher.register("completion.acceptEmployeeTask", _handler(
            AcceptEmployeeTaskHandler(EmployeeGate(), uow), AcceptEmployeeTask))
        self._dispatcher.register("completion.completeDepartmentTask", _handler(
            CompleteDepartmentTaskHandler(DepartmentGate(), uow), CompleteDepartmentTask))
        self._dispatcher.register("completion.completeCompanyTask", _handler(
            CompleteCompanyTaskHandler(CompanyGate(), uow), CompleteCompanyTask))

        logger.info("lifecycle: registered %d review/completion handlers", self._dispatcher.method_count)

    async def _ensure_profile_identity(self) -> None:
        prepared = self._prepared
        if prepared is None:
            raise RuntimeError("LIFECYCLE_INVALID: profile not prepared")
        cursor = await self._writer.execute(
            "SELECT id, schema_epoch, backend_origin, app_user_id, "
            "masked_identifier, device_id, created_at, last_opened_at "
            "FROM local_profile"
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("PROFILE_NOT_FOUND: no local_profile record")
        expected_backend = self._backend_origin
        expected_user = self._app_user_id
        expected_masked = self._masked_identifier
        expected_device = self._device_id
        mismatches = []
        if row["backend_origin"] != expected_backend:
            mismatches.append("backend_origin")
        if row["app_user_id"] != expected_user:
            mismatches.append("app_user_id")
        if row["masked_identifier"] != expected_masked:
            mismatches.append("masked_identifier")
        if row["device_id"] != expected_device:
            mismatches.append("device_id")
        if mismatches:
            raise RuntimeError(
                f"PROFILE_IDENTITY_MISMATCH: {', '.join(mismatches)}"
            )
        now = _now_iso()
        await self._writer.execute(
            "UPDATE local_profile SET last_opened_at=? WHERE id=?",
            (now, row["id"]),
        )
        await self._writer.commit()
        logger.info(
            "lifecycle: profile identity verified (backend=%s, user=%s)",
            expected_backend, expected_user,
        )

    async def health(self) -> HealthSnapshot:
        return await health_snapshot_async(
            writer=self._writer,
            write_queue=self._write_queue,
            workers=self._workers,
            db_dir=self._profile_path.parent,
        )

    async def _handle_system_health(self, params: dict[str, object], session: object = None) -> dict[str, object]:
        snapshot = await self.health()
        return {
            "status": snapshot.status,
            "observed_at": snapshot.observed_at,
            "migration_version": snapshot.profile.migration_version,
            "write_depth": snapshot.queues.write_depth,
            "workers": [(w.name, w.state) for w in snapshot.workers],
            "disk_free_bytes": snapshot.disk_free_bytes,
        }

    async def _handle_system_shutdown(self, params: dict[str, object], session: object = None) -> dict[str, object]:
        asyncio.get_event_loop().call_soon(self._shutdown_called)
        return {"status": "shutting_down"}

    def _shutdown_called(self) -> None:
        logger.info("system.shutdown requested")

    async def _heartbeat_loop(self) -> None:
        """Tick heartbeat every 5 s so event-loop lag is observable."""
        while True:
            try:
                await asyncio.sleep(5.0)
                tick_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("heartbeat loop error")
