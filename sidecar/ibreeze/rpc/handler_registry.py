from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import aiosqlite

from ibreeze.persistence.write_queue import WriteQueue
from ibreeze.rpc.dispatcher import Dispatcher

logger = logging.getLogger(__name__)

_TRACE_ID = UUID(int=0)


class _LocalDBWrapper:
    """Mimics the LocalDB interface needed by legacy RPCServer internals."""

    def __init__(self, writer: aiosqlite.Connection, profile_path: str | Path) -> None:
        self._writer = writer
        self.db_path = Path(profile_path)

    @property
    def write_connection(self) -> aiosqlite.Connection:
        return self._writer

    async def fetch_val(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        cursor = await self._writer.execute(sql, params)
        row = await cursor.fetchone()
        return row[0] if row else None

    async def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        cursor = await self._writer.execute(sql, params)
        row = await cursor.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

    async def execute_write(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Cursor:
        cursor = await self._writer.execute(sql, params)
        await self._writer.commit()
        return cursor


def _read_wrapper(handler: Any) -> Any:
    async def wrapped(params: dict[str, Any], session: object) -> Any:
        return await handler(params)
    return wrapped


def _write_wrapper_factory(handler: Any, method_name: str, write_queue: WriteQueue) -> Any:
    async def wrapped(params: dict[str, Any], session: object) -> Any:
        async def _exec(_conn: aiosqlite.Connection) -> Any:
            return await handler(params)
        return await write_queue.submit(
            "legacy." + method_name,
            _TRACE_ID,
            datetime.now(UTC) + timedelta(seconds=30),
            _exec,
        )
    return wrapped


_LEGACY_SKIP_PREFIXES = frozenset({
    "review.",
    "completion.",
    "rework.",
})


def register_legacy_handlers(
    dispatcher: Dispatcher,
    writer: aiosqlite.Connection,
    profile_path: Path,
    write_queue: WriteQueue | None = None,
) -> int:
    from ibreeze.rpc_server import READ_METHODS, RPCServer

    db_wrapper = _LocalDBWrapper(writer, profile_path)
    old_server = RPCServer(
        db=db_wrapper,  # type: ignore[arg-type]
        socket_path="/tmp/_ibreeze_legacy_bridge.sock",
        startup_token=b"\x00" * 32,
        launch_id="00000000-0000-0000-0000-000000000000",
        app_version="0.0.0",
        write_queue=write_queue,
    )

    count = 0
    skipped = 0
    for method_name, handler in old_server.methods.items():
        if any(method_name.startswith(prefix) for prefix in _LEGACY_SKIP_PREFIXES):
            skipped += 1
            continue
        if dispatcher.has_method(method_name):
            skipped += 1
            continue
        if method_name in READ_METHODS or write_queue is None:
            dispatcher.register(method_name, _read_wrapper(handler))
        else:
            dispatcher.register(
                method_name,
                _write_wrapper_factory(handler, method_name, write_queue),
            )
        count += 1

    logger.info(
        "handler_registry: registered %d legacy handlers, skipped %d (already have modern handlers)",
        count, skipped,
    )
    return count
