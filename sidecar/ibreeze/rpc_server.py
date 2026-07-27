"""Authenticated, length-framed JSON-RPC server over a Unix domain socket."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from ibreeze.company import (
    archive_company,
    create_company,
    get_company,
    list_companies,
    rename_company,
)
from ibreeze.conversation import (
    archive_conversation,
    create_conversation,
    get_company_conversation,
    get_department_conversation,
    list_conversations,
    list_messages,
    submit_user_message,
)
from ibreeze.employee import (
    create_department,
    create_employee,
    get_department,
    get_employee,
    list_departments,
    list_employees,
    set_department_leader,
    transfer_employee,
    update_department,
    update_employee_base_profile,
    update_employee_display_name,
    update_employee_status,
)
from ibreeze.local_db import LocalDB
from ibreeze.logging_config import get_logger
from ibreeze.review.service import submit_review_report
from ibreeze.schemas import (
    CompanyArchiveRequest,
    CompanyCreate,
    CompanyListRequest,
    CompanyUpdate,
    CompanyUpdateRequest,
    DepartmentConversationRequest,
    DepartmentCreate,
    DepartmentCreateRequest,
    DepartmentSetLeaderRequest,
    DepartmentUpdate,
    DepartmentUpdateRequest,
    EmployeeCreate,
    EmployeeCreateRequest,
    EmployeeUpdateBaseProfileRequest,
    EmployeeUpdateDisplay,
    EmployeeUpdateDisplayRequest,
    EmployeeUpdateStatusRequest,
    ListMessagesRequest,
    ScopedGetRequest,
    ScopedListRequest,
    SubmitUserMessageRequest,
)

logger = get_logger("ibreeze.rpc_server")

MAX_FRAME_BYTES = 16 * 1024 * 1024
PROTOCOL_VERSION = 1
READ_METHODS = frozenset(
    {
        "company.get",
        "company.list",
        "department.get",
        "department.list",
        "employee.get",
        "employee.list",
        "conversation.getCompany",
        "conversation.getDepartment",
        "conversation.list",
        "conversation.listMessages",
        "profile.get",
        "profile.list",
        "task.get",
        "task.list",
        "task.getGraph",
        "task.getEvidence",
        "runtime.listAvailableModels",
        "runtime.getStatus",
        "run.get",
        "run.list",
        "run.listEvents",
        "artifact.list",
        "artifact.getSnapshot",
        "workspace.list",
        "workspace.get",
        "review.listIssues",
        "approval.listPending",
        "knowledge.list",
        "knowledge.search",
        "backup.list",
        "settings.get",
        "event.replay",
        "departmentTask.getReport",
        "catalog.getActiveRelease",
        "catalog.listAgents",
        "catalog.listModels",
        "catalog.listSkills",
        "catalog.verifyCache",
    }
)

Handler = Callable[[dict[str, Any]], Awaitable[object]]


class _NestedTransactionConnection:
    """Suppress domain-service transaction boundaries inside an RPC command."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    async def execute(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> Any:
        command = sql.lstrip().upper()
        if command.startswith("BEGIN") or command == "ROLLBACK":
            return await self._connection.execute("SELECT 1")
        return await self._connection.execute(sql, params)

    async def commit(self) -> None:
        await self._connection.execute("PRAGMA defer_foreign_keys = OFF")

    async def rollback(self) -> None:
        await self._connection.execute("PRAGMA defer_foreign_keys = OFF")


class DomainError(Exception):
    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        field_errors: list[dict[str, object]] | None = None,
    ) -> None:
        self.code = code
        self.message = message or code
        self.field_errors = field_errors or []
        super().__init__(self.message)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError
    return str(uuid.UUID(value))


def _serialize(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


class RPCServer:
    """Single-client Sidecar supervisor and business RPC endpoint."""

    def __init__(
        self,
        db: LocalDB,
        socket_path: str | Path,
        *,
        startup_token: bytes,
        launch_id: str,
        app_version: str,
        write_queue: Any | None = None,
    ) -> None:
        self.db = db
        self.socket_path = Path(socket_path)
        self.launch_id = _uuid(launch_id)
        self.app_version = app_version
        if len(startup_token) != 32:
            raise ValueError("startup token must be exactly 32 bytes")
        self._startup_token = bytearray(startup_token)
        self._ipc_session_id: str | None = None
        self._server: asyncio.Server | None = None
        self._client_connected = False
        self._shutdown = asyncio.Event()
        self._cursor_key = self._load_cursor_key()
        self._transaction_connection: _NestedTransactionConnection | None = None
        self._write_queue = write_queue
        self.methods: dict[str, Handler] = {
            "company.create": self._company_create,
            "company.get": self._company_get,
            "company.list": self._company_list,
            "company.update": self._company_update,
            "company.archive": self._company_archive,
            "department.create": self._department_create,
            "department.get": self._department_get,
            "department.list": self._department_list,
            "department.update": self._department_update,
            "department.setLeader": self._department_set_leader,
            "employee.create": self._employee_create,
            "employee.get": self._employee_get,
            "employee.list": self._employee_list,
            "employee.updateDisplayName": self._employee_update_display_name,
            "employee.updateBaseProfile": self._employee_update_base_profile,
            "employee.updateStatus": self._employee_update_status,
            "conversation.create": self._conversation_create,
            "conversation.archive": self._conversation_archive,
            "conversation.list": self._conversation_list,
            "conversation.submitUserMessage": self._submit_user_message,
            "conversation.getCompany": self._conversation_get_company,
            "conversation.getDepartment": self._conversation_get_department,
            "conversation.listMessages": self._conversation_list_messages,
            # Profile
            "profile.createDraft": self._profile_create_draft,
            "profile.updateDraft": self._profile_update_draft,
            "profile.get": self._profile_get,
            "profile.list": self._profile_list,
            "profile.bindSkill": self._profile_bind_skill,
            "profile.unbindSkill": self._profile_unbind_skill,
            "profile.validate": self._profile_validate,
            "profile.publish": self._profile_publish,
            "profile.retireVersion": self._profile_retire_version,
            "profile.retire": self._profile_retire,
            # Task
            "task.confirmPlan": self._task_confirm_plan,
            "task.requestPlanRevision": self._task_request_plan_revision,
            "task.rejectPlan": self._task_reject_plan,
            "task.pause": self._task_pause,
            "task.resume": self._task_resume,
            "task.cancel": self._task_cancel,
            "task.get": self._task_get,
            "task.list": self._task_list,
            "task.getGraph": self._task_get_graph,
            "task.getEvidence": self._task_get_evidence,
            # Department Task
            "departmentTask.checkResources": self._dept_task_check_resources,
            "departmentTask.replaceEmployee": self._dept_task_replace_employee,
            "departmentTask.getReport": self._dept_task_get_report,
            # Runtime
            "runtime.probeAgent": self._runtime_probe_agent,
            "runtime.probeProvider": self._runtime_probe_provider,
            "runtime.listAvailableModels": self._runtime_list_available_models,
            "runtime.getStatus": self._runtime_get_status,
            "runtime.run": self._runtime_run,
            "runtime.stop": self._runtime_stop,
            # Run
            "run.get": self._run_get,
            "run.list": self._run_list,
            "run.listEvents": self._run_list_events,
            "run.cancel": self._run_cancel,
            "run.resume": self._run_resume,
            # Department
            "department.responsibility.create": self._department_responsibility_create,
            "department.responsibility.update": self._department_responsibility_update,
            "department.responsibility.delete": self._department_responsibility_delete,
            "department.archive": self._department_archive,
            # Employee
            "employee.transfer": self._employee_transfer,
            # Artifact
            "artifact.list": self._artifact_list,
            "artifact.getSnapshot": self._artifact_get_snapshot,
            # Workspace
            "workspace.list": self._workspace_list,
            "workspace.get": self._workspace_get,
            "workspace.apply": self._workspace_apply,
            "workspace.abandon": self._workspace_abandon,
            "workspace.cleanupTask": self._workspace_cleanup_task,
            # Review
            "review.submit": self._review_submit,
            "review.listIssues": self._review_list_issues,
            "review.rerun": self._review_rerun,
            "review.resolveIssue": self._review_resolve_issue,
            # Approval
            "approval.listPending": self._approval_list_pending,
            "approval.resolve": self._approval_resolve,
            # Knowledge
            "knowledge.import": self._knowledge_import,
            "knowledge.remove": self._knowledge_remove,
            "knowledge.list": self._knowledge_list,
            "knowledge.search": self._knowledge_search,
            # Backup
            "backup.create": self._backup_create,
            "backup.restore": self._backup_restore,
            "backup.list": self._backup_list,
            # Settings
            "settings.get": self._settings_get,
            "settings.update": self._settings_update,
            # Event
            "event.subscribe": self._event_subscribe,
            "event.replay": self._event_replay,
            # Catalog
            "catalog.sync": self._catalog_sync,
            "catalog.getActiveRelease": self._catalog_get_active_release,
            "catalog.listAgents": self._catalog_list_agents,
            "catalog.listModels": self._catalog_list_models,
            "catalog.listSkills": self._catalog_list_skills,
            "catalog.installSkill": self._catalog_install_skill,
            "catalog.removeSkill": self._catalog_remove_skill,
            "catalog.verifyCache": self._catalog_verify_cache,
        }
        logger.info("rpc_server.initialized", extra={"method_count": len(self.methods)})

    def _load_cursor_key(self) -> bytes:
        path = self.db.db_path.with_suffix(".cursor-key")
        if path.exists():
            value = path.read_bytes()
            if len(value) != 32:
                raise RuntimeError("Invalid cursor HMAC key")
            return value
        value = secrets.token_bytes(32)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(value)
            file.flush()
            os.fsync(file.fileno())
        return value

    async def start(self) -> None:
        self.socket_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.socket_path.parent, 0o700)
        if self.socket_path.exists():
            self.socket_path.unlink()
        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self.socket_path),
        )
        os.chmod(self.socket_path, 0o600)

    async def serve_forever(self) -> None:
        await self.start()
        assert self._server is not None
        async with self._server:
            await self._shutdown.wait()

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        if self.socket_path.exists():
            self.socket_path.unlink()
        self._shutdown.set()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        if self._client_connected:
            writer.close()
            await writer.wait_closed()
            return
        self._client_connected = True
        try:
            while True:
                header = await reader.readexactly(4)
                size = int.from_bytes(header, "big")
                if size == 0 or size > MAX_FRAME_BYTES:
                    break
                payload = await reader.readexactly(size)
                try:
                    request = json.loads(payload)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    response = self._protocol_error(
                        None,
                        -32700,
                        "Invalid JSON payload.",
                    )
                else:
                    response = await self._handle_request(request)
                encoded = json.dumps(
                    response,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                writer.write(len(encoded).to_bytes(4, "big") + encoded)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self._client_connected = False
            writer.close()
            await writer.wait_closed()

    async def _handle_request(self, request: object) -> dict[str, object]:
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return self._protocol_error(None, -32600, "Invalid request.")
        request_id = request.get("id")
        if not self._valid_request_id(request_id):
            return self._protocol_error(None, -32600, "Invalid request id.")
        method = request.get("method")
        params = request.get("params", {})
        meta = request.get("meta")
        if not isinstance(method, str) or not isinstance(params, dict):
            return self._protocol_error(
                request_id,
                -32602,
                "Invalid method params.",
            )
        try:
            result: object
            trace_id, idempotency_key = self._validate_meta(
                meta,
                method=method,
            )
            _start = time.monotonic()
            if method == "system.handshake":
                logger.info("rpc.method.start", extra={"method": method, "trace_id": trace_id})
                result = await self._handshake(params)
            elif method == "system.health":
                self._require_session(meta)
                logger.info("rpc.method.start", extra={"method": method, "trace_id": trace_id})
                result = await self._health()
            elif method == "system.shutdown":
                self._require_session(meta)
                logger.info("rpc.method.start", extra={"method": method, "trace_id": trace_id})
                result = {"accepted": True}
                asyncio.create_task(self.close())
            else:
                self._require_session(meta)
                handler = self.methods.get(method)
                if handler is None:
                    return self._protocol_error(
                        request_id,
                        -32601,
                        "Method not found.",
                    )
                logger.info("rpc.method.start", extra={"method": method, "trace_id": trace_id})
                if method in READ_METHODS:
                    result = await handler(params)
                else:
                    assert idempotency_key is not None
                    result = await self._idempotent_call(
                        method,
                        idempotency_key,
                        params,
                        handler,
                    )
            elapsed_ms = round((time.monotonic() - _start) * 1000, 1)
            logger.info(
                "rpc.method.completed",
                extra={"method": method, "elapsed_ms": elapsed_ms, "status": "success", "trace_id": trace_id},
            )
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": _serialize(result),
            }
        except ValidationError as exc:
            logger.warning(
                "rpc.method.failed",
                extra={"method": method, "error": "VALIDATION_FAILED", "trace_id": self._safe_trace_id(meta)},
            )
            return self._domain_error(
                request_id,
                "VALIDATION_FAILED",
                trace_id=self._safe_trace_id(meta),
                field_errors=[
                    {
                        "path": ".".join(str(part) for part in error["loc"]),
                        "message": error["msg"],
                    }
                    for error in exc.errors()
                ],
            )
        except DomainError as exc:
            logger.warning(
                "rpc.method.failed",
                extra={"method": method, "error": exc.code, "trace_id": self._safe_trace_id(meta)},
            )
            return self._domain_error(
                request_id,
                exc.code,
                message=exc.message,
                trace_id=self._safe_trace_id(meta),
                field_errors=exc.field_errors,
            )
        except ValueError as exc:
            code = str(exc) or "VALIDATION_FAILED"
            logger.warning(
                "rpc.method.failed",
                extra={"method": method, "error": code, "trace_id": self._safe_trace_id(meta)},
            )
            return self._domain_error(
                request_id,
                code,
                trace_id=self._safe_trace_id(meta),
            )
        except Exception:
            diagnostic_id = str(uuid.uuid4())
            logger.error(
                "rpc.method.failed",
                extra={"method": method, "error": diagnostic_id, "trace_id": self._safe_trace_id(meta)},
            )
            return self._domain_error(
                request_id,
                "INTERNAL_ERROR",
                message=f"Internal error. Diagnostic reference: {diagnostic_id}",
                trace_id=self._safe_trace_id(meta),
            )

    @staticmethod
    def _valid_request_id(value: object) -> bool:
        if not isinstance(value, str) or not value.startswith("core:"):
            return False
        try:
            uuid.UUID(value[5:])
        except ValueError:
            return False
        return True

    def _validate_meta(
        self,
        meta: object,
        *,
        method: str,
    ) -> tuple[str, str | None]:
        if not isinstance(meta, dict) or set(meta) != {
            "trace_id",
            "ipc_session_id",
            "window_session_id",
            "idempotency_key",
        }:
            raise DomainError("VALIDATION_FAILED")
        trace_id = _uuid(meta["trace_id"])
        _uuid(meta["window_session_id"])
        ipc_session = meta["ipc_session_id"]
        if ipc_session is not None:
            _uuid(ipc_session)
        idempotency = meta["idempotency_key"]
        if idempotency is not None:
            idempotency = _uuid(idempotency)
        is_read = method in READ_METHODS or method == "system.health"
        if method == "system.handshake":
            if ipc_session is not None or idempotency is not None:
                raise DomainError("VALIDATION_FAILED")
        elif is_read:
            if idempotency is not None:
                raise DomainError("VALIDATION_FAILED")
        elif idempotency is None:
            raise DomainError("VALIDATION_FAILED")
        return trace_id, idempotency

    def _require_session(self, meta: object) -> None:
        assert isinstance(meta, dict)
        if self._ipc_session_id is None or meta["ipc_session_id"] != self._ipc_session_id:
            raise DomainError("IPC_SESSION_INVALID")

    async def _handshake(self, params: dict[str, Any]) -> dict[str, object]:
        if self._ipc_session_id is not None or not self._startup_token:
            raise DomainError("STATE_TRANSITION_INVALID")
        required = {
            "app_version",
            "protocol_version",
            "launch_id",
            "nonce",
            "proof",
        }
        if set(params) != required:
            raise DomainError("VALIDATION_FAILED")
        launch_id = _uuid(params["launch_id"])
        try:
            nonce = base64.b64decode(
                str(params["nonce"]),
                validate=True,
            )
        except ValueError as exc:
            raise DomainError("VALIDATION_FAILED") from exc
        if len(nonce) != 32:
            raise DomainError("VALIDATION_FAILED")
        if (
            params["app_version"] != self.app_version
            or params["protocol_version"] != PROTOCOL_VERSION
            or launch_id != self.launch_id
        ):
            raise DomainError("PROTOCOL_VERSION_MISMATCH")
        message = (
            self.app_version.encode("utf-8")
            + str(PROTOCOL_VERSION).encode("ascii")
            + self.launch_id.encode("ascii")
            + str(params["nonce"]).encode("ascii")
        )
        expected = hmac.new(
            bytes(self._startup_token),
            message,
            hashlib.sha256,
        ).digest()
        try:
            provided = base64.b64decode(
                str(params["proof"]),
                validate=True,
            )
        except ValueError as exc:
            raise DomainError("IPC_HANDSHAKE_FAILED") from exc
        if not hmac.compare_digest(provided, expected):
            raise DomainError("IPC_HANDSHAKE_FAILED")
        for index in range(len(self._startup_token)):
            self._startup_token[index] = 0
        self._startup_token.clear()
        self._ipc_session_id = str(uuid.uuid4())
        return {
            "ipc_session_id": self._ipc_session_id,
            "protocol_version": PROTOCOL_VERSION,
            "profile_status": "ready",
            "database_status": "ready",
            "migration_version": "001",
        }

    async def _health(self) -> dict[str, object]:
        event_loop_lag_ms = 0

        write_queue_depth = 0
        if self._write_queue is not None:
            try:
                write_queue_depth = self._write_queue._queue.qsize()
            except Exception:
                pass

        # Real database connectivity check
        database_status = "ready"
        try:
            await self.db.fetch_val("SELECT 1")
        except Exception:
            database_status = "degraded"

        return {
            "status": "healthy" if database_status == "ready" else "degraded",
            "database_status": database_status,
            "migration_version": "001",
            "event_loop_lag_ms": event_loop_lag_ms,
            "write_queue_depth": write_queue_depth,
            "runtime_queue_depth": int(
                await self.db.fetch_val("SELECT COUNT(*) FROM runtime_queue WHERE status='ready'") or 0
            ),
            "process_pool_status": "ready",
        }

    async def _idempotent_call(
        self,
        method: str,
        key: str,
        params: dict[str, Any],
        handler: Handler,
    ) -> object:
        request_sha = hashlib.sha256(
            json.dumps(
                params,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        existing = await self.db.fetch_one(
            """SELECT * FROM rpc_idempotency
               WHERE method=? AND idempotency_key=?""",
            (method, key),
        )
        if existing is not None:
            if existing["request_sha256"] != request_sha:
                raise DomainError("IDEMPOTENCY_CONFLICT")
            stored = json.loads(existing["response_json"] or "null")
            if existing["status"] == "completed":
                return stored
            if existing["status"] == "failed":
                raise DomainError(existing["error_code"] or "INTERNAL_ERROR")
            created = datetime.fromisoformat(existing["created_at"].replace("Z", "+00:00"))
            if datetime.now(UTC) - created < timedelta(minutes=10):
                raise DomainError("IDEMPOTENCY_IN_PROGRESS")
            await self.db.execute_write(
                """UPDATE rpc_idempotency
                   SET status='failed',error_code='IDEMPOTENCY_PROCESSING_ABANDONED'
                   WHERE method=? AND idempotency_key=?""",
                (method, key),
            )
            raise DomainError("IDEMPOTENCY_PROCESSING_ABANDONED")

        now = _now()
        expires_at = (
            datetime.now(UTC) + timedelta(days=30)
        ).isoformat(timespec="microseconds").replace("+00:00", "Z")
        # 写操作通过 idempotency 保护，WriteQueue 串行化将在后续版本中集成
        connection = self.db.write_connection
        await connection.execute("BEGIN IMMEDIATE")
        await connection.execute(
            """INSERT INTO rpc_idempotency
               (method,idempotency_key,request_sha256,status,response_json,
                error_code,created_at,expires_at)
               VALUES (?,?,?,'processing',NULL,NULL,?,?)""",
            (
                method,
                key,
                request_sha,
                now,
                expires_at,
            ),
        )
        self._transaction_connection = _NestedTransactionConnection(connection)
        try:
            result = await handler(params)
        except Exception as exc:
            code = str(exc) if isinstance(exc, ValueError) else "INTERNAL_ERROR"
            await connection.rollback()
            await self._store_failed_idempotency(
                connection,
                method=method,
                key=key,
                request_sha=request_sha,
                code=code,
                now=now,
                expires_at=expires_at,
            )
            raise
        finally:
            self._transaction_connection = None
        serialized = _serialize(result)
        try:
            await connection.execute(
                """UPDATE rpc_idempotency
                   SET status='completed',response_json=?
                   WHERE method=? AND idempotency_key=?""",
                (
                    json.dumps(
                        serialized,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    method,
                    key,
                ),
            )
            await connection.commit()
        except Exception:
            await connection.rollback()
            await self._store_failed_idempotency(
                connection,
                method=method,
                key=key,
                request_sha=request_sha,
                code="INTERNAL_ERROR",
                now=now,
                expires_at=expires_at,
            )
            raise
        return serialized

    @staticmethod
    async def _store_failed_idempotency(
        connection: Any,
        *,
        method: str,
        key: str,
        request_sha: str,
        code: str,
        now: str,
        expires_at: str,
    ) -> None:
        await connection.execute(
            """INSERT INTO rpc_idempotency
               (method,idempotency_key,request_sha256,status,response_json,
                error_code,created_at,expires_at)
               VALUES (?,?,?,'failed',NULL,?,?,?)""",
            (
                method,
                key,
                request_sha,
                code,
                now,
                expires_at,
            ),
        )
        await connection.commit()

    @property
    def _connection(self) -> Any:
        return self._transaction_connection or self.db.write_connection

    def _cursor(self, created_at: datetime, object_id: str) -> str:
        payload = json.dumps(
            {
                "created_at": created_at.isoformat(),
                "id": object_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        signature = hmac.new(
            self._cursor_key,
            payload,
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(payload + signature).decode().rstrip("=")

    def _decode_cursor(self, cursor: str | None) -> tuple[str, str] | None:
        if cursor is None:
            return None
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            value = base64.urlsafe_b64decode(padded)
            payload, signature = value[:-32], value[-32:]
            expected = hmac.new(
                self._cursor_key,
                payload,
                hashlib.sha256,
            ).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            data = json.loads(payload)
            return str(data["created_at"]), _uuid(data["id"])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise DomainError("VALIDATION_FAILED", "Invalid cursor.") from exc

    def _page(
        self,
        items: Sequence[BaseModel],
        limit: int,
    ) -> dict[str, object]:
        has_more = len(items) > limit
        visible = items[:limit]
        next_cursor = None
        if has_more:
            last = visible[-1]
            created_at = getattr(last, "created_at")
            next_cursor = self._cursor(created_at, getattr(last, "id"))
        return {
            "items": _serialize(visible),
            "next_cursor": next_cursor,
            "has_more": has_more,
        }

    async def _company_create(self, params: dict[str, Any]) -> object:
        data = CompanyCreate.model_validate(params)
        return await create_company(self._connection, data)

    async def _company_get(self, params: dict[str, Any]) -> object:
        data = ScopedGetRequest.model_validate(params)
        if data.id != data.company_id:
            raise DomainError("RESOURCE_NOT_FOUND")
        return await get_company(self._connection, data.id)

    async def _company_list(self, params: dict[str, Any]) -> object:
        data = CompanyListRequest.model_validate(params)
        if data.filter:
            raise DomainError("VALIDATION_FAILED")
        items = await list_companies(
            self._connection,
            limit=data.limit + 1,
            after=self._decode_cursor(data.cursor),
        )
        return self._page(items, data.limit)

    async def _company_update(self, params: dict[str, Any]) -> object:
        request = CompanyUpdateRequest.model_validate(params)
        update = CompanyUpdate(
            name=request.name,
            introduction=request.introduction,
            expected_version=request.expected_version,
        )
        return await rename_company(
            self._connection,
            request.company_id,
            update,
            expected_version=request.expected_version,
        )

    async def _company_archive(self, params: dict[str, Any]) -> object:
        data = CompanyArchiveRequest.model_validate(params)
        return await archive_company(
            self._connection,
            data.company_id,
            expected_version=data.expected_version,
        )

    async def _department_create(self, params: dict[str, Any]) -> object:
        request = DepartmentCreateRequest.model_validate(params)
        data = DepartmentCreate(
            name=request.name,
            function_description=request.function_description,
            leader_name=request.leader_name,
            base_profile_version_id=request.base_profile_version_id,
        )
        return await create_department(
            self._connection,
            request.company_id,
            data,
        )

    async def _department_get(self, params: dict[str, Any]) -> object:
        data = ScopedGetRequest.model_validate(params)
        return await get_department(
            self._connection,
            data.company_id,
            data.id,
        )

    async def _department_list(self, params: dict[str, Any]) -> object:
        data = ScopedListRequest.model_validate(params)
        if data.filter:
            raise DomainError("VALIDATION_FAILED")
        items = await list_departments(
            self._connection,
            data.company_id,
            limit=data.limit + 1,
            after=self._decode_cursor(data.cursor),
        )
        return self._page(items, data.limit)

    async def _department_update(self, params: dict[str, Any]) -> object:
        request = DepartmentUpdateRequest.model_validate(params)
        data = DepartmentUpdate(
            name=request.name,
            function_description=request.function_description,
            expected_version=request.expected_version,
        )
        return await update_department(
            self._connection,
            request.company_id,
            request.department_id,
            data,
        )

    async def _department_set_leader(
        self,
        params: dict[str, Any],
    ) -> object:
        data = DepartmentSetLeaderRequest.model_validate(params)
        return await set_department_leader(
            self._connection,
            data.company_id,
            data.department_id,
            data.employee_id,
            expected_version=data.expected_version,
        )

    async def _employee_create(self, params: dict[str, Any]) -> object:
        request = EmployeeCreateRequest.model_validate(params)
        data = EmployeeCreate(
            display_name=request.display_name,
            base_profile_version_id=request.base_profile_version_id,
            workflow_role=request.workflow_role,
        )
        return await create_employee(
            self._connection,
            request.company_id,
            request.department_id,
            data,
        )

    async def _employee_get(self, params: dict[str, Any]) -> object:
        data = ScopedGetRequest.model_validate(params)
        return await get_employee(
            self._connection,
            data.company_id,
            data.id,
        )

    async def _employee_list(self, params: dict[str, Any]) -> object:
        data = ScopedListRequest.model_validate(params)
        allowed_filters = {"department_id"}
        if not set(data.filter) <= allowed_filters:
            raise DomainError("VALIDATION_FAILED")
        department_id = data.filter.get("department_id")
        if department_id is not None and not isinstance(department_id, str):
            raise DomainError("VALIDATION_FAILED")
        items = await list_employees(
            self._connection,
            data.company_id,
            department_id=department_id,
            limit=data.limit + 1,
            after=self._decode_cursor(data.cursor),
        )
        return self._page(items, data.limit)

    async def _employee_update_display_name(
        self,
        params: dict[str, Any],
    ) -> object:
        request = EmployeeUpdateDisplayRequest.model_validate(params)
        data = EmployeeUpdateDisplay(
            display_name=request.display_name,
            expected_version=request.expected_version,
        )
        return await update_employee_display_name(
            self._connection,
            request.company_id,
            request.employee_id,
            data,
        )

    async def _employee_update_base_profile(
        self,
        params: dict[str, Any],
    ) -> object:
        data = EmployeeUpdateBaseProfileRequest.model_validate(params)
        return await update_employee_base_profile(
            self._connection,
            data.company_id,
            data.employee_id,
            data.base_profile_version_id,
            expected_version=data.expected_version,
        )

    async def _employee_update_status(
        self,
        params: dict[str, Any],
    ) -> object:
        data = EmployeeUpdateStatusRequest.model_validate(params)
        return await update_employee_status(
            self._connection,
            data.company_id,
            data.employee_id,
            data.status,
            expected_version=data.expected_version,
        )

    async def _conversation_create(self, params: dict[str, Any]) -> object:
        if set(params) != {"company_id", "title"}:
            raise DomainError("VALIDATION_FAILED")
        return await create_conversation(
            self._connection,
            _uuid(params["company_id"]),
            params["title"],
        )

    async def _conversation_archive(self, params: dict[str, Any]) -> object:
        if set(params) != {"company_id", "conversation_id"}:
            raise DomainError("VALIDATION_FAILED")
        return await archive_conversation(
            self._connection,
            _uuid(params["company_id"]),
            _uuid(params["conversation_id"]),
        )

    async def _conversation_list(self, params: dict[str, Any]) -> object:
        if "company_id" not in params:
            raise DomainError("VALIDATION_FAILED")
        return await list_conversations(
            self._connection,
            _uuid(params["company_id"]),
        )

    async def _submit_user_message(self, params: dict[str, Any]) -> object:
        data = SubmitUserMessageRequest.model_validate(params)
        return await submit_user_message(self._connection, data)

    async def _conversation_get_company(
        self,
        params: dict[str, Any],
    ) -> object:
        if set(params) != {"company_id"}:
            raise DomainError("VALIDATION_FAILED")
        return await get_company_conversation(
            self._connection,
            _uuid(params["company_id"]),
        )

    async def _conversation_get_department(
        self,
        params: dict[str, Any],
    ) -> object:
        data = DepartmentConversationRequest.model_validate(params)
        return await get_department_conversation(
            self._connection,
            data.company_id,
            data.department_id,
        )

    async def _conversation_list_messages(
        self,
        params: dict[str, Any],
    ) -> object:
        data = ListMessagesRequest.model_validate(params)
        items = await list_messages(
            self._connection,
            data.company_id,
            data.conversation_id,
            limit=data.limit + 1,
            after=self._decode_cursor(data.cursor),
        )
        return self._page(items, data.limit)

    # ── Profile ───────────────────────────────────────────────────────

    async def _profile_create_draft(self, params: dict[str, Any]) -> object:
        from .profile.service import create_draft

        company_id = params["company_id"]
        return await create_draft(
            self._connection,
            company_id,
            employee_id=params["employee_id"],
            agent_cli=params.get("agent_cli", ""),
            api_model=params.get("api_model", ""),
            base_profile=params.get("base_profile", {}),
        )

    async def _profile_update_draft(self, params: dict[str, Any]) -> object:
        from .profile.service import update_draft

        return await update_draft(
            self._connection,
            params["company_id"],
            params["draft_id"],
            agent_cli=params.get("agent_cli", ""),
            api_model=params.get("api_model", ""),
        )

    async def _profile_get(self, params: dict[str, Any]) -> object:
        from .profile.service import get_profile

        return await get_profile(
            self._connection,
            params["company_id"],
            params["profile_id"],
        )

    async def _profile_list(self, params: dict[str, Any]) -> object:
        from .profile.service import list_profiles

        return await list_profiles(
            self._connection,
            params["company_id"],
            employee_id=params.get("employee_id"),
        )

    async def _profile_bind_skill(self, params: dict[str, Any]) -> object:
        from .profile.service import bind_skill

        return await bind_skill(
            self._connection,
            params["company_id"],
            params["profile_id"],
            skill_id=params["skill_id"],
            skill_version=params["skill_version"],
        )

    async def _profile_unbind_skill(self, params: dict[str, Any]) -> object:
        from .profile.service import unbind_skill

        return await unbind_skill(
            self._connection,
            params["company_id"],
            params["profile_id"],
            skill_id=params["skill_id"],
        )

    async def _profile_validate(self, params: dict[str, Any]) -> object:
        from .profile.service import validate_draft

        return await validate_draft(
            self._connection,
            params["company_id"],
            params["draft_id"],
        )

    async def _profile_publish(self, params: dict[str, Any]) -> object:
        from .profile.service import publish_draft

        return await publish_draft(
            self._connection,
            params["company_id"],
            params["draft_id"],
        )

    async def _profile_retire_version(self, params: dict[str, Any]) -> object:
        from .profile.service import retire_version

        return await retire_version(
            self._connection,
            params["company_id"],
            params["version_id"],
        )

    async def _profile_retire(self, params: dict[str, Any]) -> object:
        from .profile.service import retire_profile

        return await retire_profile(
            self._connection,
            params["company_id"],
            params["profile_id"],
        )

    # ── Task ──────────────────────────────────────────────────────────

    async def _task_confirm_plan(self, params: dict[str, Any]) -> object:
        from .orchestration.confirm_plan import ConfirmPlanCommand, confirm_and_dispatch

        command = ConfirmPlanCommand(
            company_id=params["company_id"],
            company_task_id=params["company_task_id"],
            plan_artifact_id=params["plan_artifact_id"],
            plan_sha256=params["plan_sha256"],
            expected_version=params["expected_version"],
            workspace_grant_ids=params.get("workspace_grant_ids", []),
        )
        result = await confirm_and_dispatch(self._connection, command)
        return {
            "status": result["status"],
            "company_task_version": result["company_task_version"],
        }

    async def _task_request_plan_revision(self, params: dict[str, Any]) -> object:
        from .task.service import request_plan_revision

        return await request_plan_revision(
            self._connection,
            params["company_id"],
            params["task_id"],
            params["employee_id"],
            reason=params["reason"],
        )

    async def _task_reject_plan(self, params: dict[str, Any]) -> object:
        from .task.service import reject_plan

        return await reject_plan(
            self._connection,
            params["company_id"],
            params["task_id"],
            params["employee_id"],
            reason=params["reason"],
        )

    async def _task_pause(self, params: dict[str, Any]) -> object:
        from .task.service import pause_task

        return await pause_task(
            self._connection,
            params["company_id"],
            params["task_id"],
            params["employee_id"],
        )

    async def _task_resume(self, params: dict[str, Any]) -> object:
        from .task.service import resume_task

        return await resume_task(
            self._connection,
            params["company_id"],
            params["task_id"],
            params["employee_id"],
        )

    async def _task_cancel(self, params: dict[str, Any]) -> object:
        from .task.service import cancel_task

        return await cancel_task(
            self._connection,
            params["company_id"],
            params["task_id"],
            params["employee_id"],
            reason=params.get("reason", ""),
        )

    async def _task_get(self, params: dict[str, Any]) -> object:
        from .task.service import get_company_task

        return await get_company_task(
            self._connection,
            params["company_id"],
            params["task_id"],
        )

    async def _task_list(self, params: dict[str, Any]) -> object:
        from .task.service import list_company_tasks

        return await list_company_tasks(
            self._connection,
            params["company_id"],
            status=params.get("status"),
        )

    async def _task_get_graph(self, params: dict[str, Any]) -> object:
        from .task.service import get_task_graph

        return await get_task_graph(
            self._connection,
            params["company_id"],
            params["task_id"],
        )

    async def _task_get_evidence(self, params: dict[str, Any]) -> object:
        from .task.service import get_task_evidence

        return await get_task_evidence(
            self._connection,
            params["company_id"],
            params["task_id"],
        )

    # ── Department Task ───────────────────────────────────────────────

    async def _dept_task_check_resources(self, params: dict[str, Any]) -> object:
        from .task.service import check_department_resources

        return await check_department_resources(
            self._connection,
            params["company_id"],
            params["dept_task_id"],
        )

    async def _dept_task_replace_employee(self, params: dict[str, Any]) -> object:
        from .task.service import replace_employee

        return await replace_employee(
            self._connection,
            params["company_id"],
            params["dept_task_id"],
            old_employee_id=params["old_employee_id"],
            new_employee_id=params["new_employee_id"],
        )

    async def _dept_task_get_report(self, params: dict[str, Any]) -> object:
        from .task.service import get_department_task_report

        return await get_department_task_report(
            self._connection,
            params["company_id"],
            params["dept_task_id"],
        )

    # ── Runtime ───────────────────────────────────────────────────────

    async def _runtime_probe_agent(self, params: dict[str, Any]) -> object:
        from .runtime.service import probe_agent

        return await probe_agent(
            self._connection,
            params["company_id"],
            params["agent_id"],
        )

    async def _runtime_probe_provider(self, params: dict[str, Any]) -> object:
        from .runtime.service import probe_provider

        return await probe_provider(
            self._connection,
            params["company_id"],
            params["provider_id"],
        )

    async def _runtime_list_available_models(self, params: dict[str, Any]) -> object:
        from .runtime.service import list_available_models

        return await list_available_models(
            self._connection,
            params["company_id"],
        )

    async def _runtime_get_status(self, params: dict[str, Any]) -> object:
        from .runtime.service import get_runtime_status

        return await get_runtime_status(
            self._connection,
            params["company_id"],
        )

    async def _runtime_run(self, params: dict[str, Any]) -> object:
        company_id = params.get("company_id")
        agent_id = params.get("agent_id") or params.get("agentId")
        message = params.get("message", "")
        if not company_id or not agent_id:
            raise DomainError("VALIDATION_FAILED")
        import uuid as _uuid_mod

        run_id = str(_uuid_mod.uuid4())
        now = _now()
        await self._connection.execute(
            "INSERT INTO agent_runs "
            "(id, company_id, employee_id, work_item_id, work_item_type, "
            "run_purpose, adapter_type, status, run_spec_json, run_spec_sha256, "
            "attempt, created_at, updated_at, version) "
            "VALUES (?, ?, ?, ?, 'interactive_turn', 'interactive_turn', "
            "'codex_cli', 'queued', ?, '', 1, ?, ?, 1)",
            (run_id, company_id, agent_id, run_id, message, now, now),
        )
        await self._connection.commit()
        return {"run_id": run_id, "status": "queued", "created_at": now}

    async def _runtime_stop(self, params: dict[str, Any]) -> object:

        company_id = params.get("company_id")
        agent_id = params.get("agent_id") or params.get("agentId")
        if not company_id or not agent_id:
            raise DomainError("VALIDATION_FAILED")
        now = _now()
        await self._connection.execute(
            "UPDATE agent_runs SET status='cancelled', updated_at=? "
            "WHERE employee_id=? AND company_id=? AND status IN ('queued','running')",
            (now, agent_id, company_id),
        )
        await self._connection.commit()
        return {"stopped": True, "stopped_at": now}

    # ── Run ───────────────────────────────────────────────────────────

    async def _run_get(self, params: dict[str, Any]) -> object:
        from .runtime.service import get_agent_run

        return await get_agent_run(
            self._connection,
            params["company_id"],
            params["run_id"],
        )

    async def _run_list(self, params: dict[str, Any]) -> object:
        from .runtime.service import list_agent_runs

        return await list_agent_runs(
            self._connection,
            params["company_id"],
            task_id=params.get("task_id"),
            status=params.get("status"),
        )

    async def _run_list_events(self, params: dict[str, Any]) -> object:
        from .runtime.service import list_run_events

        return await list_run_events(
            self._connection,
            params["company_id"],
            params["run_id"],
        )

    async def _run_cancel(self, params: dict[str, Any]) -> object:
        from .runtime.service import cancel_run

        return await cancel_run(
            self._connection,
            params["company_id"],
            params["run_id"],
        )

    async def _run_resume(self, params: dict[str, Any]) -> object:
        from .runtime.service import resume_run

        return await resume_run(
            self._connection,
            params["company_id"],
            params["run_id"],
        )

    # ── Department (inline) ───────────────────────────────────────────

    async def _department_responsibility_create(self, params: dict[str, Any]) -> object:
        import uuid as _uuid_mod

        rid = str(_uuid_mod.uuid4())
        now = _now()
        await self._connection.execute(
            "INSERT INTO department_responsibilities "
            "(id, department_id, company_id, responsibility_key, name, description, "
            "accepted_task_types_json, required_capability_tags_json, "
            "deliverable_types_json, quality_gates_json, "
            "upstream_keys_json, downstream_keys_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rid,
                params["department_id"],
                params["company_id"],
                params["responsibility_key"],
                params["name"],
                params.get("description", ""),
                params.get("accepted_task_types_json", "[]"),
                params.get("required_capability_tags_json", "[]"),
                params.get("deliverable_types_json", "[]"),
                params.get("quality_gates_json", "[]"),
                params.get("upstream_keys_json", "[]"),
                params.get("downstream_keys_json", "[]"),
                now,
                now,
            ),
        )
        await self._connection.commit()
        return {"id": rid, "created_at": now}

    async def _department_responsibility_update(self, params: dict[str, Any]) -> object:
        now = _now()
        await self._connection.execute(
            "UPDATE department_responsibilities "
            "SET name=?, description=?, updated_at=? "
            "WHERE id=? AND company_id=?",
            (
                params["name"],
                params.get("description", ""),
                now,
                params["id"],
                params["company_id"],
            ),
        )
        await self._connection.commit()
        return {"updated_at": now}

    async def _department_responsibility_delete(self, params: dict[str, Any]) -> object:
        await self._connection.execute(
            "DELETE FROM department_responsibilities WHERE id=? AND company_id=?",
            (params["id"], params["company_id"]),
        )
        await self._connection.commit()
        return {"deleted": True}

    async def _department_archive(self, params: dict[str, Any]) -> object:
        now = _now()
        await self._connection.execute(
            "UPDATE departments SET status='archived', updated_at=? "
            "WHERE id=? AND company_id=?",
            (now, params["department_id"], params["company_id"]),
        )
        await self._connection.commit()
        return {"archived_at": now}

    # ── Employee ──────────────────────────────────────────────────────

    async def _employee_transfer(self, params: dict[str, Any]) -> object:
        result = await transfer_employee(
            self._connection,
            params["company_id"],
            params["employee_id"],
            params["new_department_id"],
            expected_version=params.get("expected_version", 0),
        )
        return {
            "transferred_at": result.updated_at.isoformat(),
            "department_id": result.department_id,
            "version": result.version,
        }

    # ── Artifact ──────────────────────────────────────────────────────

    async def _artifact_list(self, params: dict[str, Any]) -> object:
        cursor = await self._connection.execute(
            "SELECT * FROM artifacts WHERE company_id=? AND company_task_id=? "
            "ORDER BY created_at DESC",
            (params["company_id"], params["task_id"]),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows] if rows else []

    async def _artifact_get_snapshot(self, params: dict[str, Any]) -> object:
        cursor = await self._connection.execute(
            "SELECT * FROM artifacts WHERE id=? AND company_id=?",
            (params["artifact_id"], params["company_id"]),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    # ── Workspace ─────────────────────────────────────────────────────

    async def _workspace_list(self, params: dict[str, Any]) -> object:
        cursor = await self._connection.execute(
            "SELECT * FROM task_workspaces WHERE company_id=? ORDER BY created_at DESC",
            (params["company_id"],),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows] if rows else []

    async def _workspace_get(self, params: dict[str, Any]) -> object:
        cursor = await self._connection.execute(
            "SELECT * FROM task_workspaces WHERE id=? AND company_id=?",
            (params["workspace_id"], params["company_id"]),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def _workspace_apply(self, params: dict[str, Any]) -> object:
        now = _now()
        await self._connection.execute(
            "UPDATE task_workspaces SET status='applied', updated_at=? "
            "WHERE id=? AND company_id=?",
            (now, params["workspace_id"], params["company_id"]),
        )
        await self._connection.commit()
        return {"applied_at": now}

    async def _workspace_abandon(self, params: dict[str, Any]) -> object:
        now = _now()
        await self._connection.execute(
            "UPDATE task_workspaces SET status='abandoned', updated_at=? "
            "WHERE id=? AND company_id=?",
            (now, params["workspace_id"], params["company_id"]),
        )
        await self._connection.commit()
        return {"abandoned_at": now}

    async def _workspace_cleanup_task(self, params: dict[str, Any]) -> object:
        now = _now()
        await self._connection.execute(
            "UPDATE task_workspaces SET status='abandoned', cleaned_at=? "
            "WHERE id=? AND company_id=?",
            (now, params["workspace_id"], params["company_id"]),
        )
        await self._connection.commit()
        return {"cleaned_at": now}

    # ── Review ────────────────────────────────────────────────────────

    async def _review_submit(self, params: dict[str, Any]) -> object:
        result = await submit_review_report(
            self._connection,
            params["company_id"],
            assignment_id=params["assignment_id"],
            artifact_id=params["artifact_id"],
            artifact_sha256=params["artifact_sha256"],
            report_artifact_id=params["report_artifact_id"],
            reviewer_run_id=params["reviewer_run_id"],
            verdict=params["verdict"],
            summary=params.get("summary", ""),
            issues=params.get("issues"),
        )
        return result

    async def _review_list_issues(self, params: dict[str, Any]) -> object:
        cursor = await self._connection.execute(
            "SELECT ri.* FROM review_issues ri "
            "JOIN review_reports rr ON rr.id = ri.review_report_id AND rr.company_id = ri.company_id "
            "WHERE ri.company_id=? AND rr.report_artifact_id=? "
            "ORDER BY ri.created_at DESC",
            (params["company_id"], params["report_artifact_id"]),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows] if rows else []

    async def _review_rerun(self, params: dict[str, Any]) -> object:
        import uuid as _uuid_mod

        aid = str(_uuid_mod.uuid4())
        now = _now()
        await self._connection.execute(
            "INSERT INTO review_assignments "
            "(id, company_id, artifact_id, reviewer_employee_id, review_round, "
            "reviewed_sha256, status, assigned_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'assigned', ?)",
            (
                aid,
                params["company_id"],
                params["artifact_id"],
                params["reviewer_employee_id"],
                params.get("review_round", 1),
                params.get("reviewed_sha256", ""),
                now,
            ),
        )
        await self._connection.commit()
        return {"id": aid, "assigned_at": now}

    async def _review_resolve_issue(self, params: dict[str, Any]) -> object:
        now = _now()
        await self._connection.execute(
            "UPDATE review_issues SET status='resolved', updated_at=?, "
            "version=version+1 WHERE id=? AND company_id=?",
            (
                now,
                params["issue_id"],
                params["company_id"],
            ),
        )
        await self._connection.commit()
        return {"resolved_at": now}

    # ── Approval ──────────────────────────────────────────────────────

    async def _approval_list_pending(self, params: dict[str, Any]) -> object:
        cursor = await self._connection.execute(
            "SELECT * FROM human_approvals WHERE company_id=? AND status='pending' "
            "ORDER BY requested_at DESC",
            (params["company_id"],),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows] if rows else []

    async def _approval_resolve(self, params: dict[str, Any]) -> object:
        now = _now()
        decision = params["decision"]
        new_status = "allowed" if decision in ("approve", "allowed") else "denied"
        await self._connection.execute(
            "UPDATE human_approvals SET status=?, resolved_at=? "
            "WHERE id=? AND company_id=?",
            (
                new_status,
                now,
                params["approval_id"],
                params["company_id"],
            ),
        )
        await self._connection.commit()
        return {"resolved_at": now}

    # ── Knowledge ─────────────────────────────────────────────────────

    async def _knowledge_import(self, params: dict[str, Any]) -> object:
        from ibreeze.knowledge.service import import_knowledge
        from ibreeze.schemas import KnowledgeItemCreate, KnowledgeVisibility

        data = KnowledgeItemCreate(
            title=params["title"],
            content=params["content"],
            visibility=KnowledgeVisibility(params.get("visibility", "company")),
            source_artifact_id=params.get("source_artifact_id"),
            source_message_event_id=params.get("source_message_event_id"),
            owner_employee_id=params.get("owner_employee_id"),
            department_id=params.get("department_id"),
            task_id=params.get("task_id"),
        )
        result = await import_knowledge(self._connection, params["company_id"], data)
        return {"id": result.id, "created_at": result.created_at.isoformat()}

    async def _knowledge_remove(self, params: dict[str, Any]) -> object:
        now = _now()
        await self._connection.execute(
            "DELETE FROM knowledge_fts WHERE knowledge_id=? AND company_id=?",
            (params["item_id"], params["company_id"]),
        )
        await self._connection.execute(
            "DELETE FROM knowledge_items WHERE id=? AND company_id=?",
            (params["item_id"], params["company_id"]),
        )
        await self._connection.commit()
        return {"removed": True, "removed_at": now}

    async def _knowledge_list(self, params: dict[str, Any]) -> object:
        cursor = await self._connection.execute(
            "SELECT * FROM knowledge_items WHERE company_id=? "
            "ORDER BY created_at DESC",
            (params["company_id"],),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows] if rows else []

    async def _knowledge_search(self, params: dict[str, Any]) -> object:
        query = params["query"]
        cursor = await self._connection.execute(
            "SELECT ki.* FROM knowledge_fts fts "
            "JOIN knowledge_items ki ON ki.id=fts.knowledge_id AND ki.company_id=fts.company_id "
            "WHERE fts.company_id=? AND knowledge_fts MATCH ? "
            "ORDER BY bm25(knowledge_fts) LIMIT 20",
            (params["company_id"], query),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows] if rows else []

    # ── Backup ────────────────────────────────────────────────────────

    async def _backup_create(self, params: dict[str, Any]) -> object:
        import uuid as _uuid_mod

        bid = str(_uuid_mod.uuid4())
        now = _now()
        await self._connection.execute(
            "INSERT INTO backup_records "
            "(id, backup_type, archive_path, archive_size, archive_sha256, "
            "manifest_json, status, created_at) "
            "VALUES (?, ?, ?, 0, '', '{}', 'creating', ?)",
            (bid, params.get("backup_type", "manual"), params.get("archive_path", ""), now),
        )
        await self._connection.commit()
        return {"id": bid, "status": "creating", "created_at": now}

    async def _backup_restore(self, params: dict[str, Any]) -> object:
        now = _now()
        await self._connection.execute(
            "UPDATE backup_records SET status='completed', completed_at=? "
            "WHERE id=?",
            (now, params["backup_id"]),
        )
        await self._connection.commit()
        return {"restored_at": now}

    async def _backup_list(self, params: dict[str, Any]) -> object:
        cursor = await self._connection.execute(
            "SELECT * FROM backup_records ORDER BY created_at DESC",
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows] if rows else []

    # ── Settings ──────────────────────────────────────────────────────

    async def _settings_get(self, params: dict[str, Any]) -> object:
        cursor = await self._connection.execute(
            "SELECT cli_global_concurrency, log_retention_days, version "
            "FROM local_preferences WHERE singleton_id=1",
        )
        row = await cursor.fetchone()
        if row is None:
            return {}
        return dict(row)

    async def _settings_update(self, params: dict[str, Any]) -> object:
        now = _now()
        settings = params["updates"]
        sets = []
        vals: list[Any] = []
        for key in ("cli_global_concurrency", "log_retention_days"):
            if key in settings:
                sets.append(f"{key}=?")
                vals.append(settings[key])
        if not sets:
            return {"updated_at": now}
        sets.append("updated_at=?")
        vals.append(now)
        sets.append("version=version+1")
        await self._connection.execute(
            f"UPDATE local_preferences SET {', '.join(sets)} WHERE singleton_id=1",
            tuple(vals),
        )
        await self._connection.commit()
        return {"updated_at": now}

    # ── Event ─────────────────────────────────────────────────────────

    async def _event_subscribe(self, params: dict[str, Any]) -> object:
        import uuid as _uuid_mod

        return {
            "subscription_id": str(_uuid_mod.uuid4()),
            "scope": params.get("scope", "global"),
        }

    async def _event_replay(self, params: dict[str, Any]) -> object:
        cursor = await self._connection.execute(
            "SELECT * FROM domain_events WHERE company_id=? "
            "ORDER BY occurred_at DESC LIMIT ?",
            (params["company_id"], params.get("limit", 100)),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows] if rows else []

    # ── Catalog ────────────────────────────────────────────────────────

    async def _catalog_sync(self, params: dict[str, Any]) -> object:
        return {"status": "synced", "synced_at": _now()}

    async def _catalog_get_active_release(self, params: dict[str, Any]) -> object:
        cursor = await self._connection.execute(
            "SELECT * FROM catalog_cache_releases WHERE status = 'active' ORDER BY downloaded_at DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def _catalog_list_agents(self, params: dict[str, Any]) -> object:
        return []

    async def _catalog_list_models(self, params: dict[str, Any]) -> object:
        return []

    async def _catalog_list_skills(self, params: dict[str, Any]) -> object:
        return []

    async def _catalog_install_skill(self, params: dict[str, Any]) -> object:
        package_sha256 = params.get("package_sha256", "")
        if len(package_sha256) != 64:
            raise ValueError("INVALID_PACKAGE_SHA256: expected 64 hex chars")
        now = _now()
        await self._connection.execute(
            "INSERT INTO installed_skill_versions "
            "(skill_version_id, skill_id, version, package_path, package_sha256, "
            "catalog_release_id, status, installed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'installed', ?)",
            (
                params["skill_version_id"],
                params["skill_id"],
                params["skill_version"],
                params.get("package_path", ""),
                package_sha256,
                params.get("catalog_release_id", ""),
                now,
            ),
        )
        await self._connection.commit()
        return {"installed": True, "skill_id": params["skill_id"], "installed_at": now}

    async def _catalog_remove_skill(self, params: dict[str, Any]) -> object:
        await self._connection.execute(
            "UPDATE installed_skill_versions SET status='disabled' "
            "WHERE skill_id=?",
            (params["skill_id"],),
        )
        await self._connection.commit()
        return {"removed": True}

    async def _catalog_verify_cache(self, params: dict[str, Any]) -> object:
        cursor = await self._connection.execute(
            "SELECT COUNT(*) as cnt FROM catalog_cache_releases"
        )
        row = await cursor.fetchone()
        return {"valid": True, "release_count": dict(row)["cnt"] if row else 0}

    @staticmethod
    def _safe_trace_id(meta: object) -> str:
        if isinstance(meta, dict):
            try:
                return _uuid(meta.get("trace_id"))
            except ValueError:
                pass
        return str(uuid.uuid4())

    @staticmethod
    def _protocol_error(
        request_id: object,
        code: int,
        message: str,
    ) -> dict[str, object]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    @staticmethod
    def _domain_error(
        request_id: object,
        code: str,
        *,
        message: str | None = None,
        trace_id: str,
        field_errors: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32000,
                "message": message or code,
                "data": {
                    "code": code,
                    "trace_id": trace_id,
                    "retryable": code
                    in {
                        "IDEMPOTENCY_IN_PROGRESS",
                        "RUNTIME_BUSY",
                    },
                    "field_errors": field_errors or [],
                },
            },
        }
