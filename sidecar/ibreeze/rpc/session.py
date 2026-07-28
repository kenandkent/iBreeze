import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
    ) -> None:
        self.meta = IpcSessionMeta(
            session_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            generation=multiplexer.generation,
        )
        self._multiplexer = multiplexer
        self._writer = writer
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True

    async def call(
        self,
        method: str,
        params: dict[str, Any],
        deadline_at: float | None = None,
    ) -> Any:
        rpc_id = f"sidecar:{uuid.uuid4()}"
        deadline = deadline_at or (time.monotonic() + DEFAULT_RPC_TIMEOUT)

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
                "deadline_at": datetime.now(UTC).isoformat(),
            },
        }

        await write_frame(self._writer, request)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise IpcDeadlineExceeded("deadline exceeded before response")

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
        await write_frame(self._writer, response)

    async def start_heartbeat(self, reader: asyncio.StreamReader) -> None:
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
                    break
