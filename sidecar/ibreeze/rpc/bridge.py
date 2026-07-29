from collections.abc import Awaitable, Callable
from typing import Any

from ibreeze.rpc.dispatcher import Dispatcher, HandlerFn
from ibreeze.rpc.session import IpcSession

OldHandler = Callable[[dict[str, Any]], Awaitable[object]]


def wrap_handler(handler: OldHandler) -> HandlerFn:
    async def wrapped(params: dict[str, Any], session: IpcSession) -> Any:
        return await handler(params)
    return wrapped


def register_rpc_server_handlers(
    dispatcher: Dispatcher,
    methods: dict[str, OldHandler],
) -> int:
    count = 0
    for method_name, handler in methods.items():
        dispatcher.register(method_name, wrap_handler(handler))
        count += 1
    return count
