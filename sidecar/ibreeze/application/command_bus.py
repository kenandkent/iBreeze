from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

CommandHandler = Callable[[dict[str, Any], Any | None], Awaitable[Any]]


class InternalCommandBus:
    """In-process command bus used only by workers and domain events.

    These names are deliberately not registered in the public RPC Dispatcher.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}

    def register(self, name: str, handler: CommandHandler) -> None:
        self._handlers[name] = handler

    async def dispatch(self, name: str, payload: dict[str, Any], connection: Any | None = None) -> Any:
        handler = self._handlers.get(name)
        if handler is None:
            raise ValueError(f"INTERNAL_COMMAND_NOT_ALLOWED:{name}")
        return await handler(payload, connection)
