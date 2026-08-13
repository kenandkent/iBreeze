from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from ibreeze.rpc.dispatcher import Dispatcher, ReverseMethodTable, handle_frame
from ibreeze.rpc.multiplexer import IpcDeadlineExceededError as IpcDeadlineExceeded
from ibreeze.rpc.multiplexer import MethodNotAllowedError as MethodNotAllowed
from ibreeze.rpc.session import IpcSession


@pytest.fixture
def handler() -> AsyncMock:
    return AsyncMock(return_value={"ok": True})


@pytest.fixture
def dispatcher(handler: AsyncMock) -> Dispatcher:
    d = Dispatcher()
    d.register("sys.health", handler)
    return d


@pytest.fixture
def reverse_table(handler: AsyncMock) -> ReverseMethodTable:
    t = ReverseMethodTable()
    t.register("sys.echo", handler)
    return t


@pytest.fixture
def session() -> MagicMock:
    return MagicMock(spec=IpcSession)


class TestDispatcher:
    async def test_register_and_has_method(self, handler: AsyncMock):
        d = Dispatcher()
        assert not d.has_method("sys.health")
        d.register("sys.health", handler)
        assert d.has_method("sys.health")

    async def test_has_method_returns_false_for_unknown(self):
        d = Dispatcher()
        assert not d.has_method("nonexistent")

    async def test_register_overwrites_existing(self, handler: AsyncMock):
        d = Dispatcher()
        d.register("sys.health", handler)
        handler2 = AsyncMock(return_value={"changed": True})
        d.register("sys.health", handler2)
        assert d.has_method("sys.health")

    async def test_dispatch_success(self, dispatcher: Dispatcher, handler: AsyncMock, session: MagicMock):
        result = await dispatcher.dispatch("sys.health", {"ping": True}, session)
        assert result == {"ok": True}
        handler.assert_awaited_once_with({"ping": True}, session)

    async def test_dispatch_raises_method_not_allowed(self, dispatcher: Dispatcher, session: MagicMock):
        with pytest.raises(MethodNotAllowed, match="METHOD_NOT_ALLOWED: unknown.method"):
            await dispatcher.dispatch("unknown.method", {}, session)

    async def test_method_count_starts_zero(self):
        d = Dispatcher()
        assert d.method_count == 0

    async def test_method_count_increments(self, handler: AsyncMock):
        d = Dispatcher()
        assert d.method_count == 0
        d.register("a", handler)
        assert d.method_count == 1
        d.register("b", handler)
        assert d.method_count == 2

    async def test_method_count_overwrite_does_not_increase(self, handler: AsyncMock):
        d = Dispatcher()
        d.register("x", handler)
        assert d.method_count == 1
        d.register("x", handler)
        assert d.method_count == 1


class TestReverseMethodTable:
    async def test_register_and_dispatch(self, handler: AsyncMock):
        t = ReverseMethodTable()
        t.register("sys.echo", handler)
        result = await t.dispatch("sys.echo", {"msg": "hello"})
        assert result == {"ok": True}
        handler.assert_awaited_once_with({"msg": "hello"}, None)

    async def test_dispatch_raises_method_not_allowed(self):
        t = ReverseMethodTable()
        with pytest.raises(MethodNotAllowed, match="METHOD_NOT_ALLOWED: unknown"):
            await t.dispatch("unknown", {})

    async def test_has_method(self, handler: AsyncMock):
        t = ReverseMethodTable()
        assert not t.has_method("sys.echo")
        t.register("sys.echo", handler)
        assert t.has_method("sys.echo")


class TestHandleFrame:
    async def test_successful_request(self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, session: MagicMock):
        frame = {"jsonrpc": "2.0", "id": "core:1", "method": "sys.health", "params": {}}
        result = await handle_frame(frame, dispatcher, reverse_table, session)
        assert result["result"] == {"ok": True}
        assert result["id"] == "core:1"
        assert result["jsonrpc"] == "2.0"

    async def test_method_not_allowed_error(self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, session: MagicMock):
        frame = {"jsonrpc": "2.0", "id": "core:1", "method": "nonexistent", "params": {}}
        result = await handle_frame(frame, dispatcher, reverse_table, session)
        assert "error" in result
        assert result["error"]["code"] == -32000
        assert "METHOD_NOT_ALLOWED" in result["error"]["message"]

    async def test_notification_returns_none_on_success(
        self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, session: MagicMock
    ):
        frame = {"jsonrpc": "2.0", "method": "sys.health", "params": {}}
        result = await handle_frame(frame, dispatcher, reverse_table, session)
        assert result is None

    async def test_notification_returns_none_on_error(self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, session: MagicMock):
        frame = {"jsonrpc": "2.0", "method": "nonexistent", "params": {}}
        result = await handle_frame(frame, dispatcher, reverse_table, session)
        assert result is None

    async def test_missing_method_field_raises(self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, session: MagicMock):
        frame = {"jsonrpc": "2.0", "id": "core:1", "params": {}}
        with pytest.raises(MethodNotAllowed, match="method field required"):
            await handle_frame(frame, dispatcher, reverse_table, session)

    async def test_non_string_method_raises(self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, session: MagicMock):
        frame = {"jsonrpc": "2.0", "id": "core:1", "method": 123, "params": {}}
        with pytest.raises(MethodNotAllowed, match="method field required"):
            await handle_frame(frame, dispatcher, reverse_table, session)

    async def test_params_defaults_to_empty_dict(
        self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, session: MagicMock, handler: AsyncMock
    ):
        frame = {"jsonrpc": "2.0", "id": "core:1", "method": "sys.health"}
        await handle_frame(frame, dispatcher, reverse_table, session)
        handler.assert_awaited_once_with({}, session)

    async def test_non_dict_params_normalized_to_empty(
        self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, session: MagicMock, handler: AsyncMock
    ):
        frame = {"jsonrpc": "2.0", "id": "core:1", "method": "sys.health", "params": "string"}
        await handle_frame(frame, dispatcher, reverse_table, session)
        handler.assert_awaited_once_with({}, session)

    async def test_reverse_routing(self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, handler: AsyncMock, session: MagicMock):
        frame = {"jsonrpc": "2.0", "id": "sidecar:1", "method": "sys.echo", "params": {"msg": "hi"}}
        result = await handle_frame(frame, dispatcher, reverse_table, session)
        assert result["result"] == {"ok": True}
        handler.assert_awaited_once_with({"msg": "hi"}, None)

    async def test_self_connection_guard_reverse_routing(
        self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, session: MagicMock
    ):
        handler2 = AsyncMock(return_value={"echoed": True})
        reverse_table.register("sys.echo", handler2)
        frame = {"jsonrpc": "2.0", "id": "sidecar:self-test", "method": "sys.echo", "params": {"x": 1}}
        result = await handle_frame(frame, dispatcher, reverse_table, session)
        assert result["result"]["echoed"] is True

    async def test_deadline_not_exceeded_passes(
        self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, handler: AsyncMock, session: MagicMock
    ):
        future = datetime.now(UTC) + timedelta(seconds=30)
        frame = {
            "jsonrpc": "2.0",
            "id": "core:1",
            "method": "sys.health",
            "params": {},
            "meta": {"deadline_at": future.isoformat()},
        }
        result = await handle_frame(frame, dispatcher, reverse_table, session)
        assert result["result"] == {"ok": True}

    async def test_deadline_exceeded_raises(self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, session: MagicMock):
        past = datetime.now(UTC) - timedelta(seconds=10)
        frame = {
            "jsonrpc": "2.0",
            "id": "core:1",
            "method": "sys.health",
            "params": {},
            "meta": {"deadline_at": past.isoformat()},
        }
        with pytest.raises(IpcDeadlineExceeded, match="IPC_DEADLINE_EXCEEDED: sys.health"):
            await handle_frame(frame, dispatcher, reverse_table, session)

    async def test_deadline_exceeded_notification_returns_none(
        self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, session: MagicMock
    ):
        past = datetime.now(UTC) - timedelta(seconds=10)
        frame = {
            "jsonrpc": "2.0",
            "method": "sys.health",
            "params": {},
            "meta": {"deadline_at": past.isoformat()},
        }
        result = await handle_frame(frame, dispatcher, reverse_table, session)
        assert result is None

    async def test_deadline_with_timezone_offset(
        self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, handler: AsyncMock, session: MagicMock
    ):
        future = datetime.now(UTC) + timedelta(hours=1)
        future_with_offset = future.replace(tzinfo=UTC).astimezone()
        frame = {
            "jsonrpc": "2.0",
            "id": "core:1",
            "method": "sys.health",
            "params": {},
            "meta": {"deadline_at": future_with_offset.isoformat()},
        }
        result = await handle_frame(frame, dispatcher, reverse_table, session)
        assert result["result"] == {"ok": True}

    async def test_invalid_deadline_ignored(
        self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, handler: AsyncMock, session: MagicMock
    ):
        frame = {
            "jsonrpc": "2.0",
            "id": "core:1",
            "method": "sys.health",
            "params": {},
            "meta": {"deadline_at": "not-a-date"},
        }
        result = await handle_frame(frame, dispatcher, reverse_table, session)
        assert result["result"] == {"ok": True}

    async def test_missing_meta_does_not_crash(
        self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, handler: AsyncMock, session: MagicMock
    ):
        frame = {"jsonrpc": "2.0", "id": "core:1", "method": "sys.health", "params": {}}
        result = await handle_frame(frame, dispatcher, reverse_table, session)
        assert result["result"] == {"ok": True}

    async def test_non_dict_meta_ignored(
        self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, handler: AsyncMock, session: MagicMock
    ):
        frame = {"jsonrpc": "2.0", "id": "core:1", "method": "sys.health", "params": {}, "meta": "bad"}
        result = await handle_frame(frame, dispatcher, reverse_table, session)
        assert result["result"] == {"ok": True}

    async def test_exception_from_handler_returns_error(
        self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, session: MagicMock
    ):
        failing_handler = AsyncMock(side_effect=ValueError("internal error"))
        dispatcher.register("sys.broken", failing_handler)
        frame = {"jsonrpc": "2.0", "id": "core:1", "method": "sys.broken", "params": {}}
        result = await handle_frame(frame, dispatcher, reverse_table, session)
        assert "error" in result
        assert result["error"]["code"] == -32000
        assert "internal error" in result["error"]["message"]

    async def test_exception_from_notification_returns_none(
        self, dispatcher: Dispatcher, reverse_table: ReverseMethodTable, session: MagicMock
    ):
        failing_handler = AsyncMock(side_effect=ValueError("oops"))
        dispatcher.register("sys.broken", failing_handler)
        frame = {"jsonrpc": "2.0", "method": "sys.broken", "params": {}}
        result = await handle_frame(frame, dispatcher, reverse_table, session)
        assert result is None
