from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ibreeze.application.lifecycle import ApplicationLifecycle

logger = logging.getLogger(__name__)

MAX_FRAME_BYTES = 16 * 1024 * 1024
PROTOCOL_VERSION = 1


@dataclass
class _DummySession:
    pass


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
                    response = self._error(None, -32700, "Invalid JSON payload.")
                else:
                    response = await self._dispatch(request)
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

    async def _dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return self._error(None, -32600, "Invalid request.")
        request_id = request.get("id")
        if not isinstance(request_id, str):
            return self._error(None, -32600, "Invalid request id.")
        method = request.get("method")
        params = request.get("params", {})
        if not isinstance(method, str) or not isinstance(params, dict):
            return self._error(request_id, -32602, "Invalid method params.")

        try:
            if method == "system.handshake":
                result = await self._handshake(params)
            elif method == "system.health":
                hs = await self._lifecycle.health()
                result = {
                    "status": hs.status,
                    "observed_at": hs.observed_at,
                    "migration_version": hs.profile.migration_version,
                }
            elif method == "system.shutdown":
                asyncio.create_task(self.stop())
                result = {"accepted": True}
            else:
                if self._ipc_session_id is None:
                    return self._error(request_id, -32001, "IPC_SESSION_INVALID")
                if not self._lifecycle.dispatcher.has_method(method):
                    return self._error(request_id, -32601, "Method not found.")
                result = await self._lifecycle.dispatcher.dispatch(
                    method, params, _DummySession()
                )
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }
        except Exception as exc:
            return self._error(request_id, -32000, str(exc))

    async def _handshake(self, params: dict[str, Any]) -> dict[str, Any]:
        if self._ipc_session_id is not None:
            raise ValueError("STATE_TRANSITION_INVALID")
        required = {"app_version", "protocol_version", "launch_id", "nonce", "proof"}
        if set(params) != required:
            raise ValueError("VALIDATION_FAILED")
        if params["protocol_version"] != PROTOCOL_VERSION:
            raise ValueError("PROTOCOL_MISMATCH")
        expected_raw = hmac.new(
            bytes(self._startup_token),
            f"{params['app_version']}{PROTOCOL_VERSION}{params['launch_id']}{params['nonce']}".encode(),
            hashlib.sha256,
        ).digest()
        expected_b64 = base64.b64encode(expected_raw).decode("ascii")
        if not hmac.compare_digest(expected_b64, params["proof"]):
            raise ValueError("AUTHENTICATION_FAILED")

        ipc_session_id = str(uuid.uuid4())
        self._ipc_session_id = ipc_session_id
        return {
            "ipc_session_id": ipc_session_id,
            "protocol_version": PROTOCOL_VERSION,
            "profile_status": "ready",
            "database_status": "ready" if self._lifecycle.writer is not None else "unknown",
            "migration_version": "1",
        }

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
