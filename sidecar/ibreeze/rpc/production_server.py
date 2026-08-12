from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ibreeze.application.context import CommandContext
from ibreeze.application.lifecycle import ApplicationLifecycle
from ibreeze.rpc.frame import ConnectionClosedError, read_frame, write_frame
from ibreeze.rpc.multiplexer import Multiplexer
from ibreeze.rpc.public_contracts import (
    ContractValidationError,
    method_is_write,
    validate_request,
    validate_response,
)
from ibreeze.rpc.session import IpcSession
from ibreeze.runtime.process_supervisor import get_supervisor
from ibreeze.runtime.transport import publish_broker_event, set_reverse_rpc_session

logger = logging.getLogger(__name__)

MAX_FRAME_BYTES = 16 * 1024 * 1024
PROTOCOL_VERSION = 1
MAX_INFLIGHT_REQUESTS = 256


class ProductionRpcServer:
    def __init__(
        self,
        lifecycle: ApplicationLifecycle,
        socket_path: Path,
        *,
        startup_token: bytes,
        app_version: str,
        launch_id: str,
    ) -> None:
        if len(startup_token) != 32:
            raise ValueError("startup token must be exactly 32 bytes")
        self._lifecycle = lifecycle
        self._socket_path = socket_path
        self._startup_token = bytearray(startup_token)
        self._app_version = app_version
        self._launch_id = launch_id
        self._server: asyncio.Server | None = None
        self._ipc_session_id: str | None = None
        self._client_connected = False
        self._session: IpcSession | None = None
        self._write_lock = asyncio.Lock()
        self._handshake_lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._socket_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self._socket_path.parent, 0o700)
        if self._socket_path.exists():
            self._socket_path.unlink()
        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self._socket_path),
        )
        os.chmod(self._socket_path, 0o600)
        logger.info("production rpc server listening on %s", self._socket_path)

    async def serve_forever(self) -> None:
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        set_reverse_rpc_session(None)
        self._ipc_session_id = None
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            await asyncio.gather(self._heartbeat_task, return_exceptions=True)
            self._heartbeat_task = None
        if self._session is not None:
            await self._session.close()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        if self._socket_path.exists():
            self._socket_path.unlink()

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
        session = IpcSession(Multiplexer(), writer, self._write_lock)
        self._session = session
        dispatch_tasks: set[asyncio.Task[None]] = set()

        async def dispatch_and_write(value: dict[str, Any]) -> None:
            response = await self._dispatch(value, session)
            if response is not None:
                async with self._write_lock:
                    await write_frame(writer, response)

        try:
            while True:
                value = await read_frame(reader)
                if "method" in value:
                    if len(dispatch_tasks) >= MAX_INFLIGHT_REQUESTS:
                        if value.get("id") is not None:
                            async with self._write_lock:
                                await write_frame(
                                    writer,
                                    self._error(value.get("id"), -32000, "IPC_BACKPRESSURE"),
                                )
                        continue
                    task = asyncio.create_task(dispatch_and_write(value))
                    dispatch_tasks.add(task)
                    task.add_done_callback(dispatch_tasks.discard)
                elif "id" in value and ("result" in value or "error" in value):
                    session.resolve_response(value)
                else:
                    break
        except (ConnectionClosedError, asyncio.IncompleteReadError, ConnectionError, EOFError):
            pass
        finally:
            for task in dispatch_tasks:
                task.cancel()
            if dispatch_tasks:
                await asyncio.gather(*dispatch_tasks, return_exceptions=True)
            if self._heartbeat_task is not None:
                self._heartbeat_task.cancel()
                await asyncio.gather(self._heartbeat_task, return_exceptions=True)
                self._heartbeat_task = None
            session.cancel()
            set_reverse_rpc_session(None)
            session._multiplexer.bump_generation()  # connection-loss generation cleanup
            self._session = None
            self._ipc_session_id = None
            self._client_connected = False
            writer.close()
            await writer.wait_closed()

    async def _dispatch(self, request: dict[str, Any], session: IpcSession) -> dict[str, Any] | None:
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return self._error(None, -32600, "Invalid request.")
        request_id = request.get("id")
        if request_id is not None and not isinstance(request_id, str):
            return self._error(None, -32600, "Invalid request id.")
        method = request.get("method")
        params = request.get("params", {})
        if not isinstance(method, str) or not isinstance(params, dict):
            return self._error(request_id, -32602, "Invalid method params.")

        try:
            if method == "system.handshake":
                result = await self._handshake(params)
            elif method in {
                "runtime.process.registered",
                "runtime.process.output",
                "runtime.process.exited",
                "credential.http.event",
            }:
                if self._ipc_session_id is None or self._ipc_session_id != str(session.meta.session_id):
                    return self._error(request_id, -32001, "IPC_SESSION_INVALID")
                if method == "credential.http.event":
                    publish_broker_event(params)
                else:
                    await get_supervisor().handle_notification(method, params)
                if request_id is None:
                    return None
                result = {"accepted": True}
            elif method == "system.health":
                if self._ipc_session_id is None or self._ipc_session_id != str(session.meta.session_id):
                    return self._error(request_id, -32001, "IPC_SESSION_INVALID")
                hs = await self._lifecycle.health()
                result = {
                    "status": hs.status,
                    "observed_at": hs.observed_at,
                    "migration_version": hs.profile.migration_version,
                }
            elif method == "system.shutdown":
                if self._ipc_session_id is None or self._ipc_session_id != str(session.meta.session_id):
                    return self._error(request_id, -32001, "IPC_SESSION_INVALID")
                asyncio.create_task(self.stop())
                result = {"accepted": True}
            else:
                if self._ipc_session_id is None or self._ipc_session_id != str(session.meta.session_id):
                    return self._error(request_id, -32001, "IPC_SESSION_INVALID")
                if not self._lifecycle.dispatcher.has_method(method):
                    return self._error(request_id, -32601, "Method not found.")
                try:
                    # Request schemas are generated from the canonical
                    # registry and are strict at the public boundary.  The
                    # desktop and Sidecar must ship the same registry; an
                    # unknown field is a contract error, never an implicit
                    # compatibility path.
                    validate_request(method, params)
                except ContractValidationError as exc:
                    return self._error(request_id, -32602, f"VALIDATION_FAILED: {exc}")
                meta = request.get("meta")
                context = self._context_from_meta(meta, session, method)
                if "idempotency_key" in params:
                    raise ValueError("IDEMPOTENCY_KEY_MUST_BE_IN_META")
                result = await self._lifecycle.dispatcher.dispatch(method, params, context)
                try:
                    # Validate the serialized public boundary as well as the
                    # request.  Additional response fields remain tolerated
                    # for forward compatibility, while required fields and
                    # primitive/enum constraints are always enforced.
                    validate_response(method, result)
                except ContractValidationError as exc:
                    logger.error("RPC response violates canonical schema: %s: %s", method, exc)
                    return self._error(request_id, -32603, f"INTERNAL_RESPONSE_INVALID: {exc}")
            if request_id is None:
                return None
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }
        except Exception as exc:
            # JSON-RPC notifications never receive a response, including when
            # their handler rejects the payload or the event queue is full.
            # Returning an ``id: null`` error frame would be interpreted as a
            # malformed response by the Rust reader and tear down the whole
            # authenticated session.
            if request_id is None:
                logger.warning("RPC notification failed method=%s: %s", method, exc)
                return None
            return self._error(request_id, -32000, self._safe_exception_message(exc))

    def _context_from_meta(
        self,
        value: Any,
        session: IpcSession,
        method: str,
    ) -> CommandContext:
        if not isinstance(value, dict) or not isinstance(value.get("trace_id"), str):
            raise ValueError("VALIDATION_FAILED")
        allowed = {
            "trace_id",
            "ipc_session_id",
            "window_session_id",
            "idempotency_key",
            "deadline_at",
        }
        if set(value) - allowed:
            raise ValueError("VALIDATION_FAILED")
        try:
            trace_id = uuid.UUID(value["trace_id"])
            ipc_id = uuid.UUID(str(value.get("ipc_session_id")))
        except (ValueError, TypeError, AttributeError):
            raise ValueError("VALIDATION_FAILED") from None
        if str(ipc_id) != str(session.meta.session_id):
            raise ValueError("IPC_SESSION_INVALID")
        window = value.get("window_session_id")
        try:
            window_id = uuid.UUID(window) if window else None
        except (ValueError, TypeError, AttributeError):
            raise ValueError("VALIDATION_FAILED") from None
        idempotency_value = value.get("idempotency_key")
        if idempotency_value is not None:
            try:
                uuid.UUID(str(idempotency_value))
            except (ValueError, TypeError, AttributeError):
                raise ValueError("VALIDATION_FAILED") from None
        is_write = method_is_write(method)
        if is_write is True and idempotency_value is None:
            raise ValueError("IDEMPOTENCY_KEY_REQUIRED")
        if is_write is False and idempotency_value is not None:
            raise ValueError("IDEMPOTENCY_KEY_NOT_ALLOWED")
        deadline_value = value.get("deadline_at")
        if isinstance(deadline_value, str):
            try:
                deadline = datetime.fromisoformat(deadline_value)
            except ValueError:
                raise ValueError("VALIDATION_FAILED") from None
        else:
            deadline = None
        if deadline is not None:
            if deadline.tzinfo is None:
                raise ValueError("VALIDATION_FAILED")
            deadline = deadline.astimezone(UTC)
            if deadline <= datetime.now(UTC):
                raise ValueError("IPC_DEADLINE_EXCEEDED")
        return CommandContext(
            trace_id=trace_id,
            ipc_session_id=ipc_id,
            window_session_id=window_id,
            idempotency_key=(str(idempotency_value) if idempotency_value is not None else None),
            deadline_at=deadline,
        )

    async def _handshake(self, params: dict[str, Any]) -> dict[str, Any]:
        async with self._handshake_lock:
            if self._ipc_session_id is not None:
                raise ValueError("STATE_TRANSITION_INVALID")
            required = {"app_version", "protocol_version", "launch_id", "nonce", "proof"}
            if set(params) != required:
                raise ValueError("VALIDATION_FAILED")
            if params["protocol_version"] != PROTOCOL_VERSION:
                raise ValueError("PROTOCOL_MISMATCH")
            if params["app_version"] != self._app_version or params["launch_id"] != self._launch_id:
                raise ValueError("AUTHENTICATION_FAILED")
            expected_raw = hmac.new(
                bytes(self._startup_token),
                f"{params['app_version']}{PROTOCOL_VERSION}{params['launch_id']}{params['nonce']}".encode(),
                hashlib.sha256,
            ).digest()
            expected_b64 = base64.b64encode(expected_raw).decode("ascii")
            if not hmac.compare_digest(expected_b64, params["proof"]):
                raise ValueError("AUTHENTICATION_FAILED")

            health = await self._lifecycle.health()
            if health.status not in {"healthy", "degraded"}:
                raise ValueError("SIDECAR_NOT_READY")
            ipc_session_id = str(uuid.uuid4())
            self._ipc_session_id = ipc_session_id
            session = self._session
            if session is None:
                self._ipc_session_id = None
                raise ValueError("IPC_SESSION_INVALID")
            session.bind_session_id(uuid.UUID(ipc_session_id))
            set_reverse_rpc_session(session)
            if self._heartbeat_task is None or self._heartbeat_task.done():
                self._heartbeat_task = asyncio.create_task(session.start_heartbeat())
            return {
                "ipc_session_id": ipc_session_id,
                "protocol_version": PROTOCOL_VERSION,
                "profile_status": "ready" if health.profile is not None else "unknown",
                "database_status": "ready" if self._lifecycle.writer is not None else "unknown",
                "migration_version": health.profile.migration_version,
            }

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    @staticmethod
    def _safe_exception_message(error: Exception) -> str:
        """Expose stable domain codes, never provider/SQL exception text."""
        message = str(error).strip()
        if isinstance(error, ValueError) and 0 < len(message) <= 160 and all(
            character.isupper() or character.isdigit() or character in "_.:-" for character in message
        ):
            return message
        if isinstance(error, RuntimeError) and 0 < len(message) <= 160 and all(
            character.isupper() or character.isdigit() or character in "_.:-" for character in message
        ):
            return message
        return "INTERNAL_ERROR"
