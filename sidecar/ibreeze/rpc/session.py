import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ibreeze.rpc.frame import write_frame
from ibreeze.rpc.multiplexer import (
    IpcDeadlineExceededError as IpcDeadlineExceeded,
)
from ibreeze.rpc.multiplexer import (
    Multiplexer,
)

HEARTBEAT_INTERVAL = 5.0
HEARTBEAT_TIMEOUT = 3.0
MAX_MISSED_HEARTBEATS = 3
DEFAULT_RPC_TIMEOUT = 30.0


@dataclass
class IpcSessionMeta:
    session_id: uuid.UUID
    trace_id: uuid.UUID
    generation: int
    connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class IpcSession:
    def __init__(
        self,
        multiplexer: Multiplexer,
        writer: asyncio.StreamWriter,
        write_lock: asyncio.Lock | None = None,
    ) -> None:
        self.meta = IpcSessionMeta(
            session_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            generation=multiplexer.generation,
        )
        self._multiplexer = multiplexer
        self._writer = writer
        # ProductionRpcServer and reverse calls share one writer lock.  A
        # second lock would allow a response and a reverse request to
        # interleave their 4-byte frame headers on the same UDS stream.
        self._write_lock = write_lock or asyncio.Lock()
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True
        # A disconnect must wake every reverse call immediately.  Waiting for
        # the normal 30-second deadline leaves broker tasks holding their
        # credential/egress leases after the authenticated UDS has gone away.
        self._multiplexer.cancel_all("IPC_CONNECTION_LOST")

    async def close(self) -> None:
        """Close the owned stream and release all pending reverse calls."""
        self.cancel()
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except (ConnectionError, OSError):
            pass

    def bind_session_id(self, session_id: uuid.UUID) -> None:
        self.meta.session_id = session_id

    def resolve_response(self, value: dict[str, Any]) -> None:
        rpc_id = value.get("id")
        if not isinstance(rpc_id, str):
            return
        if "error" in value:
            error = value.get("error")
            message = error.get("message", "IPC_ERROR") if isinstance(error, dict) else "IPC_ERROR"
            self._multiplexer.resolve_pending(rpc_id, error=str(message))
        else:
            self._multiplexer.resolve_pending(rpc_id, result=value.get("result"))

    async def call(
        self,
        method: str,
        params: dict[str, Any],
        deadline_at: float | None = None,
    ) -> Any:
        rpc_id = f"sidecar:{uuid.uuid4()}"
        deadline = deadline_at if deadline_at is not None else (time.monotonic() + DEFAULT_RPC_TIMEOUT)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise IpcDeadlineExceeded("deadline exceeded before request")

        future = self._multiplexer.register_pending(rpc_id, deadline)

        request = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "method": method,
            "params": params,
            "meta": {
                "trace_id": str(self.meta.trace_id),
                "ipc_session_id": str(self.meta.session_id),
                "window_session_id": None,
                "idempotency_key": None,
                "deadline_at": (datetime.now(UTC) + timedelta(seconds=remaining)).isoformat(),
            },
        }

        try:
            async with self._write_lock:
                await asyncio.wait_for(write_frame(self._writer, request), timeout=remaining)
        except Exception:
            # A failed write must not leave a completed Future in the
            # multiplexer.  Otherwise a reconnect can exhaust the 256-entry
            # pending budget with requests that never reached Rust.
            self._multiplexer.cancel_pending(rpc_id)
            raise

        remaining = deadline - time.monotonic()

        try:
            result = await asyncio.wait_for(future, timeout=remaining)
            return result
        except TimeoutError:
            self._multiplexer.cancel_pending(rpc_id)
            raise IpcDeadlineExceeded("deadline exceeded")

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        async with self._write_lock:
            await write_frame(self._writer, notification)

    async def respond(self, rpc_id: str, result: Any = None, error: str | None = None) -> None:
        if error:
            response = {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32000, "message": error},
            }
        else:
            response = {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": result,
            }
        async with self._write_lock:
            await write_frame(self._writer, response)

    async def start_heartbeat(self) -> None:
        """Emit heartbeat notifications without consuming the RPC reader.

        The production server has exactly one frame reader.  Older versions
        accepted a second ``reader`` argument and raced that reader against
        ``ProductionRpcServer._handle_client``; that could steal response
        frames and strand pending calls.
        """
        missed = 0
        while not self._cancelled:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if self._cancelled:
                break
            try:
                await self.notify("system.heartbeat", {})
                missed = 0
            except Exception:
                missed += 1
                if missed >= MAX_MISSED_HEARTBEATS:
                    self.cancel()
                    break
