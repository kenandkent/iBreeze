import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC
from typing import Any

from ibreeze.rpc.frame import write_frame
from ibreeze.rpc.multiplexer import (
    IpcDeadlineExceededError as IpcDeadlineExceeded,
)
from ibreeze.rpc.multiplexer import (
    Multiplexer,
)

DEFAULT_RPC_TIMEOUT = 30.0


class ReverseClient:
    def __init__(
        self,
        multiplexer: Multiplexer,
        writer: asyncio.StreamWriter,
        session_id: uuid.UUID,
        trace_id: uuid.UUID,
    ) -> None:
        self._multiplexer = multiplexer
        self._writer = writer
        self._session_id = session_id
        self._trace_id = trace_id

    async def call(
        self,
        method: str,
        params: dict[str, Any],
        deadline_at: float | None = None,
    ) -> Any:
        rpc_id = f"sidecar:{uuid.uuid4()}"
        deadline = deadline_at or (time.monotonic() + DEFAULT_RPC_TIMEOUT)

        future = self._multiplexer.register_pending(rpc_id, deadline)

        from datetime import datetime

        request = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "method": method,
            "params": params,
            "meta": {
                "trace_id": str(self._trace_id),
                "ipc_session_id": str(self._session_id),
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

    async def stream_events(
        self,
        request_id: uuid.UUID,
        timeout: float = 60.0,
    ) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to a stream and yield events."""
        queue = self._multiplexer.register_stream(request_id)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                event = await asyncio.wait_for(
                    queue.get(),
                    timeout=deadline - time.monotonic(),
                )
                yield event
                if event.get("event") in ("completed", "failed"):
                    break
            except TimeoutError:
                break
            except Exception:
                break
        self._multiplexer.close_stream(request_id)
