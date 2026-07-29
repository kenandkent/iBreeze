"""Model transport adapters using credential/egress broker via reverse RPC.

All provider network calls go through the Rust Credential/Egress Broker
via reverse RPC. The Sidecar must NOT do direct outbound HTTP to providers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from ibreeze.runtime.model_loop import ModelTurn, ToolCall

logger = logging.getLogger(__name__)

MAX_FRAME_BYTES = 16 * 1024 * 1024
HEARTBEAT_INTERVAL = 5.0
HEARTBEAT_TIMEOUT = 15.0


@dataclass(frozen=True, slots=True)
class UsageStats:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ModelTransport(ABC):
    """Abstract base for model transport adapters."""

    @abstractmethod
    async def complete(
        self,
        messages: tuple[dict[str, object], ...],
        tool_names: tuple[str, ...],
    ) -> ModelTurn: ...

    @abstractmethod
    async def probe(self) -> bool: ...

    @abstractmethod
    def normalize_usage(self, raw_usage: dict[str, Any]) -> UsageStats: ...


def _encode_frame(obj: dict[str, object]) -> bytes:
    payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_FRAME_BYTES:
        raise RuntimeError(f"Frame exceeds max size of {MAX_FRAME_BYTES} bytes")
    return len(payload).to_bytes(4, "big") + payload


async def _read_frame(reader: asyncio.StreamReader) -> dict[str, object]:
    header = await reader.readexactly(4)
    length = int.from_bytes(header, "big")
    if length == 0 or length > MAX_FRAME_BYTES:
        raise RuntimeError(f"Invalid frame length: {length}")
    body = await reader.readexactly(length)
    obj = json.loads(body)
    if not isinstance(obj, dict):
        raise RuntimeError("Top-level frame must be a JSON object")
    return obj


class UdsConnection:
    """Authenticated UDS connection that sends/receives JSON-RPC frames."""

    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._next_id: int = 0
        self._pending: dict[str, asyncio.Future[dict[str, object]]] = {}

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_unix_connection(self._socket_path)
        _read_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        reader = self._reader
        if reader is None:
            return
        while True:
            try:
                frame = await _read_frame(reader)
                req_id = frame.get("id")
                if req_id is not None and str(req_id) in self._pending:
                    fut = self._pending.pop(str(req_id))
                    if not fut.done():
                        fut.set_result(frame)
            except (asyncio.IncompleteReadError, ConnectionError, OSError) as exc:
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(RuntimeError(f"IPC_CONNECTION_LOST: {exc}"))
                self._pending.clear()
                break
            except Exception:
                logger.exception("UDS read loop error")
                break

    async def call(self, method: str, params: dict[str, Any]) -> dict[str, object]:
        writer = self._writer
        if writer is None:
            raise RuntimeError("UDS connection not established")
        req_id = f"sidecar:{uuid4()}"
        request: dict[str, object] = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        fut: asyncio.Future[dict[str, object]] = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut
        frame = _encode_frame(request)
        writer.write(frame)
        await writer.drain()
        response = await fut
        if "error" in response:
            err = response["error"]
            if isinstance(err, dict):
                raise RuntimeError(f"RPC error: {err.get('code')} {err.get('message')}")
            raise RuntimeError(f"RPC error: {err}")
        result = response.get("result")
        if isinstance(result, dict):
            return result
        return {}

    async def close(self) -> None:
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None


_default_socket_path: str | None = None


def set_reverse_rpc_socket_path(socket_path: str | None) -> None:
    global _default_socket_path
    _default_socket_path = socket_path


def get_reverse_rpc_socket_path() -> str | None:
    return _default_socket_path


_sidecar_own_socket: str | None = None


def mark_sidecar_own_socket(path: str | None) -> None:
    global _sidecar_own_socket
    _sidecar_own_socket = path


class ReverseRpcClient:
    """RPC client that talks to the Rust Credential/Egress Broker via UDS.

    When *socket_path* is ``None`` the client runs in **stub mode** that
    returns canned responses.  In production, supply a real UDS socket path.
    """

    def __init__(self, socket_path: str | None = None) -> None:
        self._socket_path = socket_path or _default_socket_path
        self._conn: UdsConnection | None = None
        self.last_method: str | None = None
        self.last_params: dict[str, Any] | None = None

    async def _ensure_connected(self) -> UdsConnection | None:
        if self._socket_path is None:
            return None
        if _sidecar_own_socket is not None and self._socket_path == _sidecar_own_socket:
            raise RuntimeError(
                "ReverseRpcClient cannot connect to Sidecar's own UDS socket. "
                "The Rust Credential/Egress Broker must provide a separate reverse UDS endpoint."
            )
        if self._conn is None:
            self._conn = UdsConnection(self._socket_path)
            await self._conn.connect()
        return self._conn

    async def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.last_method = method
        self.last_params = params

        conn = await self._ensure_connected()
        if conn is not None:
            result = await conn.call(method, params)
            return result

        logger.warning(
            "ReverseRpcClient stub mode: Credential Broker not configured "
            "(socket_path is None). Cannot execute method=%s",
            method,
        )
        raise RuntimeError(
            "Credential Broker is not configured (socket_path is None). "
            "Set the UDS socket path to enable real RPC transport."
        )


class ReverseRpcTransport(ModelTransport):
    """Transport that goes through the Credential/Egress Broker via reverse RPC.

    Never holds an api_key directly - only a credential_ref that the Rust
    side resolves into actual credentials for the provider.

    Uses :class:`ReverseRpcClient` with an optional *socket_path* for UDS
    transport.  When *socket_path* is ``None`` the client runs in stub mode.
    """

    def __init__(
        self,
        credential_ref: str,
        model: str,
        run_id: str = "",
        provider_release_id: str = "",
        model_binding_id: str = "",
        provider_base_url: str = "",
        profile_directory_id: str = "",
        socket_path: str | None = None,
    ) -> None:
        self._credential_ref = credential_ref
        self._model = model
        self._run_id = run_id
        self._provider_release_id = provider_release_id
        self._model_binding_id = model_binding_id
        self._provider_base_url = provider_base_url
        self._profile_directory_id = profile_directory_id
        self._rpc = ReverseRpcClient(socket_path)

    async def complete(
        self,
        messages: tuple[dict[str, object], ...],
        tool_names: tuple[str, ...],
    ) -> ModelTurn:
        from datetime import UTC, datetime, timedelta

        deadline_at = (datetime.now(UTC) + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        result = await self._rpc.call("credential.http.start", {
            "run_id": self._run_id,
            "credential_ref": self._credential_ref,
            "provider_release_id": self._provider_release_id,
            "model_binding_id": self._model_binding_id,
            "protocol": "https",
            "operation": "chat",
            "relative_path": "/v1/chat/completions",
            "request": {
                "model": self._model,
                "messages": list(messages),
                "tools": list(tool_names),
            },
            "deadline_at": deadline_at,
            "provider_base_url": self._provider_base_url,
            "profile_directory_id": self._profile_directory_id,
        })
        return ModelTurn(
            content=result.get("content", ""),
            tool_calls=tuple(
                ToolCall(
                    id=tc["id"],
                    name=tc["name"],
                    arguments=tc.get("arguments", {}),
                )
                for tc in result.get("tool_calls", [])
            ),
            usage=result.get("usage", {}),
        )

    async def probe(self) -> bool:
        result = await self._rpc.call("credential.probe", {
            "credential_ref": self._credential_ref,
            "profile_directory_id": self._profile_directory_id,
        })
        return result.get("status") == "ok"

    def normalize_usage(self, raw_usage: dict[str, Any]) -> UsageStats:
        return UsageStats(
            prompt_tokens=raw_usage.get("prompt_tokens", 0),
            completion_tokens=raw_usage.get("completion_tokens", 0),
            total_tokens=raw_usage.get("total_tokens", 0),
        )


def create_transport(
    credential_ref: str,
    model: str,
    run_id: str = "",
    provider_release_id: str = "",
    model_binding_id: str = "",
    provider_base_url: str = "",
    profile_directory_id: str = "",
    socket_path: str | None = None,
) -> ReverseRpcTransport:
    """Factory function to create the appropriate model transport.

    All providers now go through the Credential/Egress Broker,
    so there is a single transport type.  Pass *socket_path* to enable
    real UDS transport; leave ``None`` for stub mode (testing).
    """
    return ReverseRpcTransport(
        credential_ref=credential_ref,
        model=model,
        run_id=run_id,
        provider_release_id=provider_release_id,
        model_binding_id=model_binding_id,
        provider_base_url=provider_base_url,
        profile_directory_id=profile_directory_id,
        socket_path=socket_path,
    )
