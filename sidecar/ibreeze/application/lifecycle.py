from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Any, cast, get_args, get_type_hints
from uuid import UUID, uuid4

import aiosqlite

from ibreeze.application.command_bus import InternalCommandBus
from ibreeze.application.completion_handlers import (
    AcceptEmployeeTaskHandler,
    CompanyGate,
    CompleteCompanyTaskHandler,
    CompleteDepartmentTaskHandler,
    DepartmentGate,
    EmployeeGate,
    StartEmployeeTaskHandler,
    SubmitEmployeeTaskHandler,
)
from ibreeze.application.context import CommandContext
from ibreeze.application.public_rpc import register_public_handlers, verify_sidecar_registry
from ibreeze.application.review_aggregation import ReviewAggregationService
from ibreeze.application.review_handlers import (
    CloseIssueHandler,
    RejectIssueHandler,
    RerunReviewHandler,
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
    RerunReview,
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
    StartEmployeeTask,
    SubmitEmployeeTask,
)
from ibreeze.observability.health import HealthSnapshot, health_snapshot_async, tick_heartbeat
from ibreeze.orchestration.dispatch_strategies import advance_employee_task_graph
from ibreeze.persistence.connection import ReadPool, open_writer
from ibreeze.persistence.migrator import prepare
from ibreeze.persistence.profile import PreparedProfileDatabase
from ibreeze.persistence.unit_of_work import UnitOfWork
from ibreeze.persistence.write_queue import WriteQueue
from ibreeze.rpc.dispatcher import Dispatcher, ReverseMethodTable
from ibreeze.runtime.transport import set_reverse_rpc_session
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
    hints = get_type_hints(command_cls)
    for f in dataclasses.fields(command_cls):
        val = params.get(f.name)
        if val is None:
            continue
        annotation = hints.get(f.name, f.type)
        uuid_annotation = annotation is UUID or UUID in get_args(annotation)
        if uuid_annotation:
            kwargs[f.name] = _dict_to_uuid(val)
        elif annotation == tuple[ReviewIssueInput, ...]:
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
                    if i.get("assignee_employee_id")
                    else None,
                )
                for i in val
            )
        else:
            kwargs[f.name] = val
    return command_cls(**kwargs)


def _handler(handler: Any, command_cls: type, write_queue: WriteQueue | None = None) -> Any:
    async def wrapped(params: dict[str, Any], session: object) -> Any:
        command = _build_command(command_cls, params)
        context = session
        if write_queue is None:
            return await handler.handle(context, command)
        trace_id = getattr(context, "trace_id", UUID(int=0))
        deadline = getattr(context, "deadline_at", None) or (datetime.now(UTC) + timedelta(seconds=30))
        return await write_queue.submit(
            command_name=command_cls.__name__, trace_id=trace_id, deadline_at=deadline,
            execute=lambda _conn: handler.handle(context, command),
        )

    return wrapped


def _submit_handler(handler: SubmitReviewHandler, write_queue: WriteQueue | None = None) -> Any:
    async def wrapped(params: dict[str, Any], session: object) -> Any:
        command = _build_command(SubmitReview, params)
        context = session
        if write_queue is None:
            return await handler.handle(context, command)
        return await write_queue.submit(
            command_name=SubmitReview.__name__,
            trace_id=getattr(context, "trace_id", UUID(int=0)),
            deadline_at=getattr(context, "deadline_at", None) or (datetime.now(UTC) + timedelta(seconds=30)),
            execute=lambda _conn: handler.handle(context, command),
        )

    return wrapped


def _internal_review_handler(handler: Any, command_cls: type) -> Any:
    """Adapt an internal review command to the current Outbox transaction.

    Internal review state transitions are never public RPCs.  OutboxWorker
    dispatches them while the WriteQueue transaction is already open, so this
    adapter must call the handler directly instead of enqueueing a nested
    WriteQueue item (which would deadlock the sole writer).
    """

    async def wrapped(params: dict[str, Any], connection: Any | None) -> Any:
        if connection is None:
            raise RuntimeError("INTERNAL_WRITE_CONNECTION_REQUIRED")
        command = _build_command(command_cls, params)
        raw_company = params.get("company_id")
        company_scope = UUID(raw_company) if isinstance(raw_company, str) else None
        context = CommandContext(
            trace_id=uuid4(),
            ipc_session_id=UUID(int=0),
            window_session_id=None,
            idempotency_key=None,
            deadline_at=datetime.now(UTC) + timedelta(seconds=30),
            company_scope=company_scope,
        )
        return await handler.handle(context, command)

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
        app_version: str = "0.0.0",
        profile_mode: str = "offline",
        launch_id: str = "",
    ) -> None:
        self._profile_path = profile_path
        self._socket_path = socket_path
        self._backend_origin = backend_origin
        self._app_user_id = app_user_id
        self._masked_identifier = masked_identifier
        self._device_id = device_id
        self._app_version = app_version
        self._profile_mode = profile_mode
        self._launch_id = launch_id
        self._phase = LifecyclePhase.INIT
        self._prepared: PreparedProfileDatabase | None = None
        self._writer: aiosqlite.Connection | None = None
        self._read_pool: ReadPool | None = None
        self._write_queue: WriteQueue | None = None
        self._unit_of_work: UnitOfWork | None = None
        self._workers: WorkerSupervisor | None = None
        self._dispatcher: Dispatcher = Dispatcher()
        self._reverse_table: ReverseMethodTable = ReverseMethodTable()
        self._command_bus = InternalCommandBus()
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._employee_accept_handler: AcceptEmployeeTaskHandler | None = None
        self._employee_start_handler: StartEmployeeTaskHandler | None = None
        self._employee_submit_handler: SubmitEmployeeTaskHandler | None = None
        self._department_complete_handler: CompleteDepartmentTaskHandler | None = None
        self._company_complete_handler: CompleteCompanyTaskHandler | None = None

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

    @property
    def command_bus(self) -> InternalCommandBus:
        return self._command_bus

    async def start(self) -> None:
        logger.info("lifecycle: acquire profile file lock")
        self._profile_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._profile_path.parent.chmod(0o700)
        self._prepared = await prepare(self._profile_path)
        self._phase = LifecyclePhase.LOCK_ACQUIRED

        # Start independent heartbeat task (ticks every 5 s so event-loop lag is measurable)
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Reverse calls reuse the authenticated ProductionRpcServer session.
        # The lifecycle must never open a second connection to its own UDS.
        set_reverse_rpc_session(None)
        if self._socket_path is not None:
            logger.info("lifecycle: waiting for authenticated reverse IPC session")
        else:
            logger.info("lifecycle: no IPC server configured")
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

        logger.info("lifecycle: prepare rpc dispatcher")

        logger.info("lifecycle: register core system handlers")
        self._dispatcher.register("system.health", self._handle_system_health)
        self._dispatcher.register("system.shutdown", self._handle_system_shutdown)

        logger.info("lifecycle: register registry review/completion handlers")
        registered = register_public_handlers(self)
        await self._init_review_completion_handlers()
        if registered:
            verify_sidecar_registry(self._dispatcher)
        for command_name in (
            "StartEmployeeTask", "EvaluateEmployeeSubmission", "EvaluateEmployeeAcceptance", "EvaluateAffectedTask",
            "EvaluateDepartmentReadiness", "EvaluateCompanyReadiness", "AdvanceEmployeeTaskGraph",
        ):
            self._command_bus.register(
                command_name,
                self._internal_command_handler(command_name),
            )
        logger.info("lifecycle: start worker supervisor")
        self._workers = WorkerSupervisor(
            writer=self._writer,
            write_queue=self._write_queue,
            read_pool=self._read_pool,
            command_bus=self._command_bus,
        )
        await self._workers.start()
        self._phase = LifecyclePhase.WORKER_SUPERVISOR_STARTED
        self._phase = LifecyclePhase.RPC_DISPATCHER_ENABLED

        logger.info("lifecycle: handshake ready")
        self._phase = LifecyclePhase.HANDSHAKE_READY

    def _internal_command_handler(
        self, command_name: str
    ) -> Callable[[dict[str, Any], Any | None], Awaitable[Any]]:
        async def handler(payload: dict[str, Any], connection: Any | None = None) -> Any:
            return await self._evaluate_internal_command(command_name, payload, connection)

        return handler

    async def _evaluate_internal_command(
        self,
        command_name: str,
        payload: dict[str, object],
        connection: Any | None = None,
    ) -> dict[str, object]:
        """Evaluate completion gates inside the Outbox transaction.

        Outbox rows carry the aggregate that changed.  We resolve that
        aggregate to the next task level and invoke the same completion
        handler used by public commands; no worker starts a second write
        transaction and no event is silently discarded.
        """
        if (
            self._employee_start_handler is None
            or
            self._employee_submit_handler is None
            or self._employee_accept_handler is None
            or self._department_complete_handler is None
            or self._company_complete_handler is None
        ):
            raise RuntimeError("INTERNAL_COMMAND_HANDLERS_UNAVAILABLE")
        db = connection or self.writer
        raw_company = payload.get("company_id")
        if not isinstance(raw_company, str):
            return {"status": "ignored", "reason": "company_id_missing"}
        # Canonical status-change events use aggregate_id.  Accept the
        # historical task_id alias only for already persisted outbox rows so
        # a restart can drain an older queue without weakening the contract.
        task_id_value = payload.get("aggregate_id") or payload.get("task_id")
        if command_name == "StartEmployeeTask":
            expected_version = payload.get("expected_version")
            if not isinstance(task_id_value, str) or not isinstance(expected_version, int):
                return {"status": "ignored", "reason": "task_id_or_version_missing"}
            start_request = StartEmployeeTask(
                UUID(raw_company),
                UUID(task_id_value),
                expected_version,
            )
            context = CommandContext(uuid4(), UUID(int=0), None, None, datetime.now(UTC) + timedelta(seconds=30))
            result = await self._employee_start_handler.handle(context, start_request)
            return cast(dict[str, object], result)
        if command_name == "EvaluateEmployeeSubmission":
            run_id = payload.get("run_id") or payload.get("aggregate_id")
            if not isinstance(run_id, str):
                return {"status": "ignored", "reason": "run_id_missing"}
            cursor = await db.execute(
                """SELECT employee_task_id, company_id, status
                   FROM agent_runs
                   WHERE id=? AND company_id=?""",
                (run_id, raw_company),
            )
            run_row = await cursor.fetchone()
            if run_row is None or run_row["status"] != "succeeded" or not run_row["employee_task_id"]:
                return {"status": "ignored", "reason": "run_not_successful_or_not_employee_task"}
            cursor = await db.execute(
                """SELECT version FROM employee_tasks
                   WHERE id=? AND company_id=?""",
                (run_row["employee_task_id"], raw_company),
            )
            task_row = await cursor.fetchone()
            if task_row is None:
                return {"status": "ignored", "reason": "employee_task_missing"}
            submit_request = SubmitEmployeeTask(
                UUID(str(raw_company)),
                UUID(str(run_row["employee_task_id"])),
                UUID(str(run_id)),
                int(task_row["version"]),
            )
            context = CommandContext(uuid4(), UUID(int=0), None, None, datetime.now(UTC) + timedelta(seconds=30))
            try:
                result = await self._employee_submit_handler.handle(context, submit_request)
                return cast(dict[str, object], result)
            except ValueError as exc:
                if str(exc) in {"OPTIMISTIC_LOCK_CONFLICT", "RESOURCE_NOT_FOUND"}:
                    return {"status": "ignored", "reason": str(exc)}
                raise
        assignment_id = payload.get("assignment_id")
        issue_id = payload.get("issue_id")
        if assignment_id or issue_id:
            source_id = assignment_id or issue_id
            cursor = await db.execute(
                """SELECT et.id AS task_id, et.version
                   FROM employee_tasks et
                   JOIN department_tasks dt ON dt.id=et.department_task_id AND dt.company_id=et.company_id
                   JOIN artifacts a ON a.company_task_id=dt.company_task_id AND a.company_id=dt.company_id
                   JOIN review_assignments ra ON ra.artifact_id=a.id
                   WHERE ra.id=? AND et.company_id=?
                   ORDER BY et.created_at LIMIT 1""",
                (str(source_id), raw_company),
            )
            row = await cursor.fetchone()
            if row is None and issue_id:
                cursor = await db.execute(
                    """SELECT et.id AS task_id, et.version
                       FROM review_issues ri
                       JOIN review_reports rr ON rr.id=ri.review_report_id
                       JOIN review_assignments ra ON ra.id=rr.assignment_id
                       JOIN artifacts a ON a.id=ra.artifact_id
                       JOIN department_tasks dt ON dt.company_task_id=a.company_task_id AND dt.company_id=a.company_id
                       JOIN employee_tasks et ON et.department_task_id=dt.id AND et.company_id=dt.company_id
                       WHERE ri.id=? AND et.company_id=?
                       ORDER BY et.created_at LIMIT 1""",
                    (str(issue_id), raw_company),
                )
                row = await cursor.fetchone()
            if row is not None:
                task_id_value = row["task_id"]
        if not isinstance(task_id_value, str):
            return {"status": "ignored", "reason": "task_id_missing"}

        if command_name == "EvaluateCompanyReadiness":
            cursor = await db.execute(
                """SELECT ct.id, ct.company_id, ct.version
                   FROM department_tasks dt JOIN company_tasks ct ON ct.id=dt.company_task_id AND ct.company_id=dt.company_id
                   WHERE dt.id=? AND dt.company_id=?""",
                (task_id_value, raw_company),
            )
            row = await cursor.fetchone()
            if row is None:
                return {"status": "ignored", "reason": "company_task_missing"}
            company_request = CompleteCompanyTask(UUID(str(row["company_id"])), UUID(str(row["id"])), int(row["version"]))
            context = CommandContext(uuid4(), UUID(int=0), None, None, datetime.now(UTC) + timedelta(seconds=30))
            try:
                result = await self._company_complete_handler.handle(context, company_request)
                return cast(dict[str, object], result)
            except ValueError as exc:
                if str(exc).startswith("COMPLETION_GATE_BLOCKED"):
                    return {"status": "blocked", "reason": str(exc)}
                raise

        # A status change from an employee task is evaluated at department
        # level; review changes are evaluated at employee level first.
        if command_name == "EvaluateDepartmentReadiness":
            cursor = await db.execute(
                """SELECT dt.id, dt.company_id, dt.version
                   FROM employee_tasks et JOIN department_tasks dt ON dt.id=et.department_task_id AND dt.company_id=et.company_id
                   WHERE et.id=? AND et.company_id=?""",
                (task_id_value, raw_company),
            )
            row = await cursor.fetchone()
            if row is None:
                return {"status": "ignored", "reason": "department_task_missing"}
            department_request = CompleteDepartmentTask(UUID(str(row["company_id"])), UUID(str(row["id"])), int(row["version"]))
            context = CommandContext(uuid4(), UUID(int=0), None, None, datetime.now(UTC) + timedelta(seconds=30))
            try:
                result = await self._department_complete_handler.handle(context, department_request)
                return cast(dict[str, object], result)
            except ValueError as exc:
                if str(exc).startswith("COMPLETION_GATE_BLOCKED"):
                    return {"status": "blocked", "reason": str(exc)}
                raise

        if command_name == "AdvanceEmployeeTaskGraph":
            # A sequential-refinement segment was accepted: dispatch every
            # dependent segment whose upstream is now fully accepted, inside
            # this Outbox transaction.  aggregate_id is the accepted task.
            if not isinstance(task_id_value, str):
                return {"status": "ignored", "reason": "task_id_missing"}
            return await advance_employee_task_graph(
                db,
                company_id=raw_company,
                accepted_task_id=task_id_value,
            )

        cursor = await db.execute(
            "SELECT id, company_id, version FROM employee_tasks WHERE id=? AND company_id=?",
            (task_id_value, raw_company),
        )
        row = await cursor.fetchone()
        if row is None:
            return {"status": "ignored", "reason": "employee_task_missing"}
        accept_request = AcceptEmployeeTask(UUID(str(row["company_id"])), UUID(str(row["id"])), int(row["version"]))
        context = CommandContext(uuid4(), UUID(int=0), None, None, datetime.now(UTC) + timedelta(seconds=30))
        try:
            result = await self._employee_accept_handler.handle(context, accept_request)
            return cast(dict[str, object], result)
        except ValueError as exc:
            if str(exc).startswith("COMPLETION_GATE_BLOCKED"):
                return {"status": "blocked", "reason": str(exc)}
            raise

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

        if self._workers is not None:
            logger.info("lifecycle: stop workers")
            await self._workers.stop()

        if self._write_queue is not None:
            logger.info("lifecycle: drain write queue (max 10s)")
            await self._write_queue.stop(timeout=10.0)

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

        wq = self._write_queue
        self._dispatcher.register("review.resolveIssue", _handler(ResolveIssueHandler(repo, uow), ResolveIssue, wq))
        guard = SubmitReviewGuards(repo)
        aggregation = ReviewAggregationService(repo)
        self._dispatcher.register(
            "review.submit",
            _submit_handler(SubmitReviewHandler(repo, guard, uow, aggregation=aggregation), wq),
        )

        # Public RPC names are exactly the names in registry.v1.json.  The
        # state-machine commands are internal and are dispatched by Outbox.
        self._dispatcher.register("review.listIssues", self._handle_review_list_issues)
        self._dispatcher.register("review.rerun", _handler(RerunReviewHandler(repo, uow), RerunReview, wq))

        # Review state-machine commands are internal by design. They are
        # registered on the same bus as completion gates so a workflow or
        # Outbox event can advance an assignment/issue without exposing a
        # caller-controlled public RPC or opening a second write transaction.
        for command_name, handler, command_cls in (
            ("StartReview", StartReviewHandler(repo, uow), StartReview),
            ("StartIssueFix", StartIssueFixHandler(repo, uow), StartIssueFix),
            ("VerifyIssue", VerifyIssueHandler(repo, uow), VerifyIssue),
            ("CloseIssue", CloseIssueHandler(repo, uow), CloseIssue),
            ("RejectIssue", RejectIssueHandler(repo, uow), RejectIssue),
        ):
            self._command_bus.register(command_name, _internal_review_handler(handler, command_cls))

        self._employee_accept_handler = AcceptEmployeeTaskHandler(EmployeeGate(), uow)
        self._employee_start_handler = StartEmployeeTaskHandler(uow)
        self._employee_submit_handler = SubmitEmployeeTaskHandler(uow)
        self._department_complete_handler = CompleteDepartmentTaskHandler(DepartmentGate(), uow)
        self._company_complete_handler = CompleteCompanyTaskHandler(CompanyGate(), uow)

        logger.info("lifecycle: registered %d review/completion handlers", self._dispatcher.method_count)

    async def _handle_review_list_issues(self, params: dict[str, object], session: object) -> dict[str, object]:
        company_id = params.get("company_id")
        review_id = params.get("review_id")
        if not isinstance(company_id, str) or not isinstance(review_id, str):
            raise ValueError("VALIDATION_FAILED")
        rows = await self.read_pool.query_all(
            """SELECT id AS issue_id, severity, status AS state, category, description,
                      verifier_employee_id, rejection_reason
               FROM review_issues
               WHERE review_report_id=? AND company_id=?
               ORDER BY created_at, id""",
            (review_id, company_id),
        )
        return {"issues": rows}

    async def _ensure_profile_identity(self) -> None:
        prepared = self._prepared
        if prepared is None:
            raise RuntimeError("LIFECYCLE_INVALID: profile not prepared")
        wq = self._write_queue
        assert wq is not None
        await wq.submit(
            command_name="ensure_profile_identity",
            trace_id=uuid4(),
            deadline_at=datetime.now(UTC).replace(year=9999),
            execute=self._ensure_profile_identity_in_transaction,
        )

    async def _ensure_profile_identity_in_transaction(self, conn: aiosqlite.Connection) -> None:
        """Read and update the profile identity inside the single write transaction."""
        cursor = await conn.execute(
            "SELECT id, schema_epoch, backend_origin, app_user_id, "
            "masked_identifier, device_id FROM local_profile"
        )
        row = await cursor.fetchone()
        if row is None:
            if self._profile_mode != "online":
                raise RuntimeError("PROFILE_NOT_FOUND: no local_profile record")
            now = _now_iso()
            await conn.execute(
                "INSERT INTO local_profile "
                "(id, schema_epoch, created_by_app_version, backend_origin, "
                "app_user_id, masked_identifier, device_id, created_at, last_opened_at) "
                "VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid4()),
                    self._app_version,
                    self._backend_origin,
                    self._app_user_id,
                    self._masked_identifier,
                    self._device_id,
                    now,
                    now,
                ),
            )
            logger.info(
                "lifecycle: profile identity initialized (backend=%s, user=%s, mode=online)",
                self._backend_origin,
                self._app_user_id,
            )
            return
        if row["schema_epoch"] != 1:
            raise RuntimeError(f"PROFILE_SCHEMA_UNSUPPORTED: schema_epoch={row['schema_epoch']}")
        expected = {
            "backend_origin": self._backend_origin,
            "app_user_id": self._app_user_id,
            "masked_identifier": self._masked_identifier,
            "device_id": self._device_id,
        }
        mismatches = [key for key, value in expected.items() if row[key] != value]
        if mismatches:
            raise RuntimeError(f"PROFILE_IDENTITY_MISMATCH: {', '.join(mismatches)}")
        await conn.execute(
            "UPDATE local_profile SET last_opened_at=? WHERE id=?",
            (_now_iso(), row["id"]),
        )
        logger.info(
            "lifecycle: profile identity verified (backend=%s, user=%s)",
            self._backend_origin,
            self._app_user_id,
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
