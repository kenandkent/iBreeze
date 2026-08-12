from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

from ibreeze.rpc.multiplexer import (
    IpcDeadlineExceededError as IpcDeadlineExceeded,
)
from ibreeze.rpc.multiplexer import (
    MethodNotAllowedError as MethodNotAllowed,
)
from ibreeze.rpc.session import IpcSession

HandlerFn = Callable[[dict[str, Any], object], Coroutine[Any, Any, Any]]


class Dispatcher:
    def __init__(self) -> None:
        self._handlers: dict[str, HandlerFn] = {}

    def register(self, method: str, handler: HandlerFn) -> None:
        self._handlers[method] = handler

    def has_method(self, method: str) -> bool:
        return method in self._handlers

    @property
    def method_count(self) -> int:
        return len(self._handlers)

    async def dispatch(
        self,
        method: str,
        params: dict[str, Any],
        session: object,
    ) -> Any:
        handler = self._handlers.get(method)
        if handler is None:
            raise MethodNotAllowed(f"METHOD_NOT_ALLOWED: {method}")
        return await handler(params, session)


class ReverseMethodTable:
    def __init__(self) -> None:
        self._handlers: dict[str, HandlerFn] = {}

    def register(self, method: str, handler: HandlerFn) -> None:
        self._handlers[method] = handler

    def has_method(self, method: str) -> bool:
        return method in self._handlers

    async def dispatch(self, method: str, params: dict[str, Any]) -> Any:
        handler = self._handlers.get(method)
        if handler is None:
            raise MethodNotAllowed(f"METHOD_NOT_ALLOWED: {method}")
        return await handler(params, None)


async def handle_frame(
    value: dict[str, Any],
    dispatcher: Dispatcher,
    reverse_table: ReverseMethodTable,
    session: IpcSession,
) -> dict[str, Any] | None:
    method = value.get("method")
    if not isinstance(method, str):
        raise MethodNotAllowed("method field required")

    params = value.get("params", {})
    if not isinstance(params, dict):
        params = {}

    is_notification = "id" not in value
    rpc_id = value.get("id")

    meta = value.get("meta", {})
    deadline_str = meta.get("deadline_at") if isinstance(meta, dict) else None

    if deadline_str:
        try:
            deadline = datetime.fromisoformat(deadline_str)
            if deadline.tzinfo is not None:
                deadline = deadline.astimezone(UTC)
            if deadline.replace(tzinfo=UTC) < datetime.now(UTC):
                if is_notification:
                    return None
                raise IpcDeadlineExceeded(f"IPC_DEADLINE_EXCEEDED: {method}")
        except (ValueError, TypeError):
            pass

    # Method registration, not the caller-controlled id, defines the
    # reverse-RPC direction.
    is_reverse = reverse_table.has_method(method)

    try:
        if is_reverse:
            result = await reverse_table.dispatch(method, params)
        else:
            result = await dispatcher.dispatch(method, params, session)
    except Exception as e:
        if is_notification:
            return None
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32000, "message": str(e)},
        }

    if is_notification:
        return None

    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "result": result,
    }
