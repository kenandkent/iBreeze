"""Sidecar RPC server tests — JSON-RPC 2.0 protocol, handler registration, error handling.

Covers design spec sections:
- H.2 JSON-RPC Server (schema validation, method registration, direction)
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_server():
    """创建一个带 mock LocalDB 的 RPCServer 实例。"""
    from ibreeze.rpc_server import RPCServer

    mock_db = MagicMock()
    mock_db.insert = AsyncMock(return_value={"id": "test-id"})
    mock_db.list_all = AsyncMock(return_value=[])
    mock_db.count = AsyncMock(return_value=0)
    mock_db.get_by_id = AsyncMock(return_value=None)
    mock_db.update_by_id = AsyncMock(return_value=None)
    mock_db.delete_by_id = AsyncMock(return_value=False)
    mock_db.search = AsyncMock(return_value=[])
    mock_db._db = None
    return RPCServer(db=mock_db)


def _run(coro):
    """同步运行 async 协程。"""
    return asyncio.run(coro)


class TestRpcServer:
    """JSON-RPC 2.0 server."""

    def test_builtin_methods_registered(self):
        """RPCServer 启动时自动注册内置方法。"""
        server = _make_server()
        assert "ping" in server.methods
        assert "health" in server.methods
        assert "version" in server.methods
        assert "company.create" in server.methods
        assert "conversation.create" in server.methods
        assert "knowledge.create" in server.methods
        assert "workspace.create" in server.methods
        assert "orchestration.create" in server.methods
        assert "employee.create" in server.methods
        assert "agent.run" in server.methods
        assert "audit.log" in server.methods

    def test_ping(self):
        server = _make_server()
        response = _run(server._handle_request({"jsonrpc": "2.0", "method": "ping", "id": 1}))
        assert response["jsonrpc"] == "2.0"
        assert response["result"]["pong"] == "pong"
        assert response["id"] == 1

    def test_method_not_found(self):
        server = _make_server()
        response = _run(server._handle_request({"jsonrpc": "2.0", "method": "nonexistent", "id": 1}))

        assert "error" in response
        assert response["error"]["code"] == -32601
        assert response["id"] == 1

    def test_handler_exception_returns_error(self):
        server = _make_server()

        async def bad_handler(_params):
            raise ValueError("boom")

        server.methods["fail"] = bad_handler
        response = _run(server._handle_request({"jsonrpc": "2.0", "method": "fail", "id": 1}))

        assert "error" in response
        assert response["error"]["code"] == -32603

    def test_params_passed_to_handler(self):
        server = _make_server()

        async def echo(params):
            return {"name": params.get("name"), "age": params.get("age")}

        server.methods["test"] = echo
        response = _run(server._handle_request({
            "jsonrpc": "2.0",
            "method": "test",
            "params": {"name": "alice", "age": 30},
            "id": 1,
        }))

        assert response["result"]["name"] == "alice"
        assert response["result"]["age"] == 30

    def test_no_params(self):
        server = _make_server()

        async def noparams(_params):
            return "fine"

        server.methods["noparams"] = noparams
        response = _run(server._handle_request({"jsonrpc": "2.0", "method": "noparams", "id": 1}))
        assert response["result"] == "fine"

    def test_missing_method_field(self):
        server = _make_server()
        response = _run(server._handle_request({"jsonrpc": "2.0", "id": 1}))
        assert response["error"]["code"] == -32601

    def test_notification_no_id(self):
        server = _make_server()

        async def notify(_params):
            return "done"

        server.methods["notify"] = notify
        response = _run(server._handle_request({"jsonrpc": "2.0", "method": "notify"}))
        assert response.get("id") is None
        assert response["result"] == "done"

    def test_multiple_handlers(self):
        server = _make_server()

        async def add(params):
            return params["a"] + params["b"]

        async def mul(params):
            return params["a"] * params["b"]

        server.methods["add"] = add
        server.methods["mul"] = mul

        r1 = _run(server._handle_request({"jsonrpc": "2.0", "method": "add", "params": {"a": 2, "b": 3}, "id": 1}))
        r2 = _run(server._handle_request({"jsonrpc": "2.0", "method": "mul", "params": {"a": 2, "b": 3}, "id": 2}))

        assert r1["result"] == 5
        assert r2["result"] == 6

    def test_overwrite_handler(self):
        server = _make_server()

        async def v1(_params):
            return "v1"

        async def v2(_params):
            return "v2"

        server.methods["test"] = v1
        server.methods["test"] = v2

        response = _run(server._handle_request({"jsonrpc": "2.0", "method": "test", "id": 1}))
        assert response["result"] == "v2"

    def test_rpc_server_has_methods_dict(self):
        server = _make_server()
        assert hasattr(server, "methods")
        assert isinstance(server.methods, dict)
