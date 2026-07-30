"""Tests for ibreeze.rpc.bridge module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ibreeze.rpc.bridge import register_rpc_server_handlers, wrap_handler
from ibreeze.rpc.dispatcher import Dispatcher


@pytest.fixture
def dispatcher() -> Dispatcher:
    return Dispatcher()


class TestWrapHandler:
    async def test_wraps_old_handler_to_new_signature(self):
        async def old_handler(params):
            return {"result": params.get("x", 0)}

        wrapped = wrap_handler(old_handler)
        result = await wrapped({"x": 42}, session=MagicMock())
        assert result == {"result": 42}

    async def test_wrapped_handler_ignores_session(self):
        async def old_handler(params):
            return params

        wrapped = wrap_handler(old_handler)
        result = await wrapped({"a": 1}, session=None)
        assert result == {"a": 1}

    async def test_wrapped_handler_propagates_exceptions(self):
        async def failing_handler(params):
            raise ValueError("boom")

        wrapped = wrap_handler(failing_handler)
        with pytest.raises(ValueError, match="boom"):
            await wrapped({}, session=None)


class TestRegisterRpcServerHandlers:
    async def test_registers_multiple_handlers(self, dispatcher: Dispatcher):
        h1 = AsyncMock(return_value={"ok": True})
        h2 = AsyncMock(return_value={"ok": False})
        methods = {"sys.health": h1, "sys.version": h2}

        count = register_rpc_server_handlers(dispatcher, methods)
        assert count == 2
        assert dispatcher.has_method("sys.health")
        assert dispatcher.has_method("sys.version")

    async def test_returns_zero_for_empty_methods(self, dispatcher: Dispatcher):
        count = register_rpc_server_handlers(dispatcher, {})
        assert count == 0

    async def test_single_handler(self, dispatcher: Dispatcher):
        h = AsyncMock(return_value="single")
        count = register_rpc_server_handlers(dispatcher, {"test.method": h})
        assert count == 1
        assert dispatcher.has_method("test.method")

    async def test_wrapped_handler_callable(self, dispatcher: Dispatcher):
        h = AsyncMock(return_value={"wrapped": True})
        register_rpc_server_handlers(dispatcher, {"test": h})
        result = await dispatcher.dispatch("test", {"key": "val"}, MagicMock())
        assert result == {"wrapped": True}
        h.assert_awaited_once_with({"key": "val"})
