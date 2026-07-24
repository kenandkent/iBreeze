"""Authenticated, length-framed JSON-RPC server over a Unix domain socket."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
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
    get_company_conversation,
    get_department_conversation,
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
    update_department,
    update_employee_base_profile,
    update_employee_display_name,
    update_employee_status,
)
from ibreeze.local_db import LocalDB
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
        "conversation.listMessages",
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
            "conversation.submitUserMessage": self._submit_user_message,
            "conversation.getCompany": self._conversation_get_company,
            "conversation.getDepartment": self._conversation_get_department,
            "conversation.listMessages": self._conversation_list_messages,
        }

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
            if method == "system.handshake":
                result = await self._handshake(params)
            elif method == "system.health":
                self._require_session(meta)
                result = await self._health()
            elif method == "system.shutdown":
                self._require_session(meta)
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
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": _serialize(result),
            }
        except ValidationError as exc:
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
            return self._domain_error(
                request_id,
                exc.code,
                message=exc.message,
                trace_id=self._safe_trace_id(meta),
                field_errors=exc.field_errors,
            )
        except ValueError as exc:
            code = str(exc) or "VALIDATION_FAILED"
            return self._domain_error(
                request_id,
                code,
                trace_id=self._safe_trace_id(meta),
            )
        except Exception:
            diagnostic_id = str(uuid.uuid4())
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
        return {
            "status": "healthy",
            "database_status": "ready",
            "migration_version": "001",
            "event_loop_lag_ms": 0,
            "write_queue_depth": 0,
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
