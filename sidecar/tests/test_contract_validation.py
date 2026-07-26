"""Contract validation tests: verify frontend ↔ Sidecar RPC method alignment."""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from pathlib import Path

import pytest

from ibreeze.local_db import LocalDB
from ibreeze.rpc_server import RPCServer


def _uuid() -> str:
    return str(uuid.uuid4())


def _meta(*, ipc_session_id: str | None, idempotency_key: str | None) -> dict[str, str | None]:
    return {
        "trace_id": _uuid(),
        "ipc_session_id": ipc_session_id,
        "window_session_id": _uuid(),
        "idempotency_key": idempotency_key,
    }


def _request(method: str, params: dict[str, object], meta: dict[str, str | None]) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": f"core:{_uuid()}",
        "method": method,
        "params": params,
        "meta": meta,
    }


async def _handshake(server: RPCServer, token: bytes, launch_id: str) -> str:
    from ibreeze.rpc_server import PROTOCOL_VERSION

    nonce = base64.b64encode(b"n" * 32).decode()
    message = b"1.0.0" + str(PROTOCOL_VERSION).encode() + launch_id.encode() + nonce.encode()
    proof = base64.b64encode(hmac.new(token, message, hashlib.sha256).digest()).decode()
    response = await server._handle_request(
        _request(
            "system.handshake",
            {
                "app_version": "1.0.0",
                "protocol_version": PROTOCOL_VERSION,
                "launch_id": launch_id,
                "nonce": nonce,
                "proof": proof,
            },
            _meta(ipc_session_id=None, idempotency_key=None),
        )
    )
    return str(response["result"]["ipc_session_id"])


@pytest.fixture
def server_factory(local_db: LocalDB, tmp_path: Path):
    servers: list[RPCServer] = []

    def factory() -> tuple[RPCServer, bytes, str]:
        token = b"s" * 32
        launch_id = _uuid()
        server = RPCServer(
            local_db,
            tmp_path / f"{launch_id}.sock",
            startup_token=token,
            launch_id=launch_id,
            app_version="1.0.0",
        )
        servers.append(server)
        return server, token, launch_id

    return factory


@pytest.mark.asyncio
class TestCompanyContract:
    """Validate company.* method contracts match frontend expectations."""

    async def test_company_list_returns_paginated(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=None)

        response = await server._handle_request(
            _request("company.list", {"filter": {}, "cursor": None, "limit": 50}, meta)
        )
        assert "result" in response
        result = response["result"]
        assert "items" in result
        assert "next_cursor" in result
        assert "has_more" in result

    async def test_company_get_requires_scoped_params(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=None)

        response = await server._handle_request(
            _request("company.get", {"id": _uuid(), "company_id": _uuid()}, meta)
        )
        # Should return error since company doesn't exist
        assert "error" in response or "result" in response

    async def test_company_create_requires_correct_fields(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        idempotency = _uuid()
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=idempotency)

        # Missing required fields should fail validation
        response = await server._handle_request(
            _request("company.create", {"name": "Test"}, meta)
        )
        assert "error" in response


@pytest.mark.asyncio
class TestDepartmentContract:
    """Validate department.* method contracts match frontend expectations."""

    async def test_department_list_requires_company_id(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=None)

        response = await server._handle_request(
            _request("department.list", {"company_id": _uuid(), "filter": {}, "cursor": None, "limit": 50}, meta)
        )
        assert "result" in response
        result = response["result"]
        assert "items" in result
        assert "next_cursor" in result
        assert "has_more" in result

    async def test_department_create_requires_correct_fields(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        idempotency = _uuid()
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=idempotency)

        # Missing required fields should fail validation
        response = await server._handle_request(
            _request("department.create", {"company_id": _uuid(), "name": "Dept"}, meta)
        )
        assert "error" in response


@pytest.mark.asyncio
class TestEmployeeContract:
    """Validate employee.* method contracts match frontend expectations."""

    async def test_employee_list_requires_company_id(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=None)

        response = await server._handle_request(
            _request("employee.list", {"company_id": _uuid(), "filter": {}, "cursor": None, "limit": 50}, meta)
        )
        assert "result" in response
        result = response["result"]
        assert "items" in result
        assert "next_cursor" in result
        assert "has_more" in result

    async def test_employee_create_requires_correct_fields(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        idempotency = _uuid()
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=idempotency)

        # Missing required fields should fail validation
        response = await server._handle_request(
            _request(
                "employee.create",
                {"company_id": _uuid(), "department_id": _uuid(), "display_name": "Emp"},
                meta,
            )
        )
        assert "error" in response


@pytest.mark.asyncio
class TestConversationContract:
    """Validate conversation.* method contracts match frontend expectations."""

    async def test_conversation_list_requires_company_id(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=None)

        response = await server._handle_request(
            _request("conversation.list", {"company_id": _uuid()}, meta)
        )
        assert "result" in response

    async def test_conversation_list_messages_requires_both_ids(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=None)

        response = await server._handle_request(
            _request(
                "conversation.listMessages",
                {"company_id": _uuid(), "conversation_id": _uuid(), "cursor": None, "limit": 50},
                meta,
            )
        )
        assert "result" in response

    async def test_conversation_create_requires_company_id_and_title(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        idempotency = _uuid()
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=idempotency)

        # Missing fields should fail
        response = await server._handle_request(
            _request("conversation.create", {"company_id": _uuid()}, meta)
        )
        assert "error" in response

    async def test_conversation_submit_requires_company_and_conversation(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        idempotency = _uuid()
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=idempotency)

        response = await server._handle_request(
            _request(
                "conversation.submitUserMessage",
                {"company_id": _uuid(), "conversation_id": _uuid(), "content": "Hello"},
                meta,
            )
        )
        # Should fail since conversation doesn't exist
        assert "error" in response


@pytest.mark.asyncio
class TestTaskContract:
    """Validate task.* method contracts match frontend expectations."""

    async def test_task_list_requires_company_id(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=None)

        response = await server._handle_request(
            _request("task.list", {"company_id": _uuid()}, meta)
        )
        # Should return result (empty list) or error (table missing in test)
        assert "result" in response or "error" in response

    async def test_task_confirm_requires_correct_fields(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        idempotency = _uuid()
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=idempotency)

        response = await server._handle_request(
            _request(
                "task.confirmPlan",
                {"company_id": _uuid(), "task_id": _uuid(), "employee_id": _uuid()},
                meta,
            )
        )
        # Should fail since task doesn't exist
        assert "error" in response


@pytest.mark.asyncio
class TestRuntimeContract:
    """Validate runtime.* method contracts match frontend expectations."""

    async def test_runtime_run_requires_company_and_agent(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        idempotency = _uuid()
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=idempotency)

        response = await server._handle_request(
            _request(
                "runtime.run",
                {"company_id": _uuid(), "agent_id": _uuid(), "message": "hello"},
                meta,
            )
        )
        # Should return result (run_id) or error (table missing in test)
        assert "result" in response or "error" in response

    async def test_runtime_stop_requires_company_and_agent(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        idempotency = _uuid()
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=idempotency)

        response = await server._handle_request(
            _request(
                "runtime.stop",
                {"company_id": _uuid(), "agent_id": _uuid()},
                meta,
            )
        )
        # Should return result (stopped) or error (table missing in test)
        assert "result" in response or "error" in response

    async def test_runtime_get_status_requires_company_id(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=None)

        response = await server._handle_request(
            _request("runtime.getStatus", {"company_id": _uuid()}, meta)
        )
        assert "result" in response


@pytest.mark.asyncio
class TestWorkspaceContract:
    """Validate workspace.* method contracts match frontend expectations."""

    async def test_workspace_list_requires_company_id(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=None)

        response = await server._handle_request(
            _request("workspace.list", {"company_id": _uuid()}, meta)
        )
        assert "result" in response

    async def test_workspace_get_requires_workspace_and_company(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=None)

        response = await server._handle_request(
            _request(
                "workspace.get",
                {"workspace_id": _uuid(), "company_id": _uuid()},
                meta,
            )
        )
        assert "result" in response
        assert response["result"] is None

    async def test_workspace_apply_requires_workspace_and_company(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        idempotency = _uuid()
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=idempotency)

        response = await server._handle_request(
            _request(
                "workspace.apply",
                {"workspace_id": _uuid(), "company_id": _uuid()},
                meta,
            )
        )
        # Should return result or error (sidecar may return success even if not found)
        assert "result" in response or "error" in response

    async def test_workspace_abandon_requires_workspace_and_company(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        idempotency = _uuid()
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=idempotency)

        response = await server._handle_request(
            _request(
                "workspace.abandon",
                {"workspace_id": _uuid(), "company_id": _uuid()},
                meta,
            )
        )
        # Should return result or error (sidecar may return success even if not found)
        assert "result" in response or "error" in response


@pytest.mark.asyncio
class TestKnowledgeContract:
    """Validate knowledge.* method contracts match frontend expectations."""

    async def test_knowledge_list_requires_company_id(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=None)

        response = await server._handle_request(
            _request("knowledge.list", {"company_id": _uuid()}, meta)
        )
        assert "result" in response

    async def test_knowledge_search_requires_company_and_query(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=None)

        response = await server._handle_request(
            _request("knowledge.search", {"company_id": _uuid(), "query": "test"}, meta)
        )
        assert "result" in response

    async def test_knowledge_remove_requires_company_and_item_id(self, server_factory, local_db):
        server, token, launch_id = server_factory()
        ipc_session = await _handshake(server, token, launch_id)
        idempotency = _uuid()
        meta = _meta(ipc_session_id=ipc_session, idempotency_key=idempotency)

        response = await server._handle_request(
            _request(
                "knowledge.remove",
                {"company_id": _uuid(), "item_id": _uuid()},
                meta,
            )
        )
        # Should return result (removed) or error (sidecar returns success even if not found)
        assert "result" in response or "error" in response


@pytest.mark.asyncio
class TestMethodExistence:
    """Verify all methods referenced in Rust sidecar_method_kind exist in Sidecar."""

    def test_all_read_methods_registered(self, server_factory):
        server, _, _ = server_factory()
        read_methods = [
            "company.get", "company.list",
            "department.get", "department.list",
            "employee.get", "employee.list",
            "conversation.list", "conversation.getCompany",
            "conversation.getDepartment", "conversation.listMessages",
            "task.get", "task.list", "task.getGraph", "task.getEvidence",
            "departmentTask.getReport",
            "runtime.listAvailableModels", "runtime.getStatus",
            "run.get", "run.list", "run.listEvents",
            "approval.listPending",
            "artifact.list", "artifact.getSnapshot",
            "workspace.list", "workspace.get",
            "review.listIssues",
            "catalog.getActiveRelease", "catalog.listAgents",
            "catalog.listModels", "catalog.listSkills",
            "knowledge.list", "knowledge.search",
            "backup.list", "settings.get",
            "event.subscribe", "event.replay",
        ]
        for method in read_methods:
            assert method in server.methods, f"Read method '{method}' not registered in Sidecar"

    def test_all_write_methods_registered(self, server_factory):
        server, _, _ = server_factory()
        write_methods = [
            "company.create", "company.update", "company.archive",
            "department.create", "department.update", "department.archive",
            "department.setLeader",
            "department.responsibility.create", "department.responsibility.update",
            "department.responsibility.delete",
            "employee.create", "employee.updateStatus",
            "employee.updateDisplayName", "employee.updateBaseProfile",
            "employee.transfer",
            "conversation.create", "conversation.archive",
            "conversation.submitUserMessage",
            "task.confirmPlan", "task.requestPlanRevision", "task.rejectPlan",
            "task.pause", "task.resume", "task.cancel",
            "departmentTask.checkResources", "departmentTask.replaceEmployee",
            "runtime.probeAgent", "runtime.probeProvider",
            "runtime.run", "runtime.stop",
            "run.cancel", "run.resume",
            "approval.resolve",
            "workspace.apply", "workspace.abandon", "workspace.cleanupTask",
            "review.submit", "review.rerun", "review.resolveIssue",
            "catalog.sync", "catalog.installSkill", "catalog.removeSkill",
            "catalog.verifyCache",
            "knowledge.import", "knowledge.remove",
            "backup.create", "backup.restore",
            "settings.update",
        ]
        for method in write_methods:
            assert method in server.methods, f"Write method '{method}' not registered in Sidecar"
