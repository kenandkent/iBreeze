"""RPC Server tests — JSON-RPC 2.0 protocol, method dispatch, business methods.

Covers design spec sections:
- H.2 JSON-RPC Server (schema validation, method registration, direction)
"""
import pytest


class TestRpcRequestHandling:
    """JSON-RPC 2.0 request handling."""

    @pytest.mark.asyncio
    async def test_handle_request_valid(self):
        from ibreeze.rpc_server import RPCServer
        from unittest.mock import AsyncMock, MagicMock

        db = AsyncMock()
        db._db = MagicMock()
        db.insert = AsyncMock(return_value={"id": "1", "name": "Test"})
        server = RPCServer(db)

        response = await server._handle_request({
            "jsonrpc": "2.0",
            "method": "ping",
            "id": 1,
        })
        assert response["jsonrpc"] == "2.0"
        assert response["result"]["pong"] == "pong"
        assert response["id"] == 1

    @pytest.mark.asyncio
    async def test_handle_request_invalid_json(self):
        from ibreeze.rpc_server import RPCServer
        from unittest.mock import AsyncMock, MagicMock

        db = AsyncMock()
        server = RPCServer(db)

        response = await server._handle_request({
            "jsonrpc": "1.0",
            "method": "ping",
            "id": 1,
        })
        assert "error" in response
        assert response["error"]["code"] == -32600

    @pytest.mark.asyncio
    async def test_handle_request_method_not_found(self):
        from ibreeze.rpc_server import RPCServer
        from unittest.mock import AsyncMock, MagicMock

        db = AsyncMock()
        server = RPCServer(db)

        response = await server._handle_request({
            "jsonrpc": "2.0",
            "method": "nonexistent.method",
            "id": 1,
        })
        assert "error" in response
        assert response["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_handle_request_missing_params(self):
        from ibreeze.rpc_server import RPCServer, RPCError
        from unittest.mock import AsyncMock, MagicMock

        db = AsyncMock()
        db.get_by_id = AsyncMock(return_value=None)
        server = RPCServer(db)

        response = await server._handle_request({
            "jsonrpc": "2.0",
            "method": "company.get",
            "params": {},
            "id": 1,
        })
        assert "error" in response
        assert response["error"]["code"] == -32602


class TestCompanyRpc:
    """Company RPC methods."""

    @pytest.mark.asyncio
    async def test_company_create_rpc(self):
        from ibreeze.rpc_server import RPCServer
        from unittest.mock import AsyncMock, MagicMock

        db = AsyncMock()
        db.insert = AsyncMock(return_value={"id": "c1", "name": "Acme"})
        server = RPCServer(db)

        response = await server._handle_request({
            "jsonrpc": "2.0",
            "method": "company.create",
            "params": {"name": "Acme"},
            "id": 1,
        })
        assert "result" in response
        assert response["result"]["name"] == "Acme"
        db.insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_company_list_rpc(self):
        from ibreeze.rpc_server import RPCServer
        from unittest.mock import AsyncMock, MagicMock

        db = AsyncMock()
        db.list_all = AsyncMock(return_value=[{"id": "c1", "name": "Acme"}])
        db.count = AsyncMock(return_value=1)
        server = RPCServer(db)

        response = await server._handle_request({
            "jsonrpc": "2.0",
            "method": "company.list",
            "params": {},
            "id": 1,
        })
        assert response["result"]["total"] == 1
        assert len(response["result"]["items"]) == 1


class TestConversationRpc:
    """Conversation RPC methods."""

    @pytest.mark.asyncio
    async def test_conversation_create_rpc(self):
        from ibreeze.rpc_server import RPCServer
        from unittest.mock import AsyncMock, MagicMock

        db = AsyncMock()
        db.insert = AsyncMock(return_value={"id": "conv1", "user_id": "u1"})
        server = RPCServer(db)

        response = await server._handle_request({
            "jsonrpc": "2.0",
            "method": "conversation.create",
            "params": {"user_id": "u1", "title": "Help"},
            "id": 1,
        })
        assert "result" in response
        assert response["result"]["user_id"] == "u1"


class TestKnowledgeRpc:
    """Knowledge RPC methods."""

    @pytest.mark.asyncio
    async def test_knowledge_create_rpc(self):
        from ibreeze.rpc_server import RPCServer
        from unittest.mock import AsyncMock, MagicMock

        db = AsyncMock()
        db._db = MagicMock()
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.description = [("id",)]
        db._db.execute = AsyncMock(return_value=cursor)
        db.insert = AsyncMock(return_value={"id": "k1", "title": "FAQ"})
        server = RPCServer(db)

        response = await server._handle_request({
            "jsonrpc": "2.0",
            "method": "knowledge.create",
            "params": {"title": "FAQ", "content": "What?", "type": "FAQ"},
            "id": 1,
        })
        assert "result" in response


class TestWorkspaceRpc:
    """Workspace RPC methods."""

    @pytest.mark.asyncio
    async def test_workspace_create_rpc(self):
        from ibreeze.rpc_server import RPCServer
        from unittest.mock import AsyncMock, MagicMock

        db = AsyncMock()
        db.insert = AsyncMock(return_value={"id": "w1", "name": "WS"})
        server = RPCServer(db)

        response = await server._handle_request({
            "jsonrpc": "2.0",
            "method": "workspace.create",
            "params": {"name": "WS", "owner_id": "u1"},
            "id": 1,
        })
        assert "result" in response
        assert response["result"]["name"] == "WS"


class TestOrchestrationRpc:
    """Orchestration RPC methods."""

    @pytest.mark.asyncio
    async def test_orchestration_create_rpc(self):
        from ibreeze.rpc_server import RPCServer
        from unittest.mock import AsyncMock, MagicMock

        db = AsyncMock()
        db.insert = AsyncMock(return_value={"id": "o1", "name": "Flow"})
        server = RPCServer(db)

        response = await server._handle_request({
            "jsonrpc": "2.0",
            "method": "orchestration.create",
            "params": {"name": "Flow"},
            "id": 1,
        })
        assert "result" in response
        assert response["result"]["name"] == "Flow"
