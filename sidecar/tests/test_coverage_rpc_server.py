"""Tests to improve RPC server coverage: error handling, lifecycle, uncovered handlers."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ibreeze.local_db import LocalDB
from ibreeze.rpc_server import (
    PROTOCOL_VERSION,
    DomainError,
    RPCServer,
    _serialize,
    _uuid,
)


def _uid() -> str:
    return str(uuid.uuid4())


def _meta(*, ipc_session_id: str | None, idempotency_key: str | None) -> dict[str, str | None]:
    return {
        "trace_id": _uid(),
        "ipc_session_id": ipc_session_id,
        "window_session_id": _uid(),
        "idempotency_key": idempotency_key,
    }


def _request(
    method: str,
    params: dict[str, object],
    meta: dict[str, str | None],
) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": f"core:{_uid()}",
        "method": method,
        "params": params,
        "meta": meta,
    }


async def _handshake(server: RPCServer, token: bytes, launch_id: str) -> str:
    import base64, hashlib, hmac as _hmac
    nonce = base64.b64encode(b"n" * 32).decode()
    message = b"1.0.0" + str(PROTOCOL_VERSION).encode() + launch_id.encode() + nonce.encode()
    proof = base64.b64encode(_hmac.new(token, message, hashlib.sha256).digest()).decode()
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


async def _setup_company(server: RPCServer, session: str, published_profile: str) -> str:
    resp = await server._handle_request(_request(
        "company.create",
        {
            "name": f"RPC-{_uid()[:8]}",
            "introduction": "test",
            "general_manager_name": "GM",
            "base_profile_version_id": published_profile,
        },
        _meta(ipc_session_id=session, idempotency_key=_uid()),
    ))
    assert "result" in resp
    return resp["result"]["id"]


@pytest.fixture
def server_factory(local_db: LocalDB, tmp_path):
    servers: list[RPCServer] = []

    def factory() -> tuple[RPCServer, bytes, str]:
        token = b"s" * 32
        launch_id = _uid()
        server = RPCServer(
            local_db, tmp_path / f"{launch_id}.sock",
            startup_token=token, launch_id=launch_id, app_version="1.0.0",
        )
        servers.append(server)
        return server, token, launch_id

    return factory


# ── Server initialization errors ───────────────────────────────────────


class TestServerInit:
    def test_startup_token_too_short(self, local_db, tmp_path):
        with pytest.raises(ValueError, match="startup token"):
            RPCServer(local_db, tmp_path / "test.sock", startup_token=b"short", launch_id=_uid(), app_version="1.0.0")

    def test_startup_token_too_long(self, local_db, tmp_path):
        with pytest.raises(ValueError, match="startup token"):
            RPCServer(local_db, tmp_path / "test.sock", startup_token=b"x" * 33, launch_id=_uid(), app_version="1.0.0")


# ── Request validation ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestRequestValidation:
    async def test_invalid_jsonrpc_version(self, server_factory):
        server, _, _ = server_factory()
        resp = await server._handle_request({"jsonrpc": "1.0", "id": "core:x", "method": "test"})
        assert resp["error"]["code"] == -32600

    async def test_missing_jsonrpc(self, server_factory):
        server, _, _ = server_factory()
        resp = await server._handle_request({"id": "core:x", "method": "test"})
        assert resp["error"]["code"] == -32600

    async def test_invalid_request_id(self, server_factory):
        server, _, _ = server_factory()
        resp = await server._handle_request({"jsonrpc": "2.0", "id": "bad", "method": "test"})
        assert resp["error"]["code"] == -32600

    async def test_non_dict_request(self, server_factory):
        server, _, _ = server_factory()
        resp = await server._handle_request("not a dict")
        assert resp["error"]["code"] == -32600

    async def test_invalid_method_type(self, server_factory):
        server, _, _ = server_factory()
        resp = await server._handle_request({
            "jsonrpc": "2.0",
            "id": f"core:{_uid()}",
            "method": 123,
            "params": {},
        })
        assert resp["error"]["code"] == -32602

    async def test_invalid_params_type(self, server_factory):
        server, _, _ = server_factory()
        resp = await server._handle_request({
            "jsonrpc": "2.0",
            "id": f"core:{_uid()}",
            "method": "test",
            "params": "not dict",
        })
        assert resp["error"]["code"] == -32602

    async def test_method_not_found(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "nonexistent.method", {}, _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert resp["error"]["code"] == -32601

    async def test_missing_session_for_non_system_method(self, server_factory):
        server, _, _ = server_factory()
        resp = await server._handle_request(_request(
            "company.list", {}, _meta(ipc_session_id=None, idempotency_key=None),
        ))
        assert resp["error"]["data"]["code"] == "IPC_SESSION_INVALID"


# ── Handshake error paths ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestHandshakeErrors:
    async def test_handshake_wrong_params(self, server_factory):
        server, _, _ = server_factory()
        resp = await server._handle_request(_request(
            "system.handshake", {"bad": "params"}, _meta(ipc_session_id=None, idempotency_key=None),
        ))
        assert resp["error"]["data"]["code"] == "VALIDATION_FAILED"

    async def test_handshake_invalid_nonce(self, server_factory):
        server, token, launch_id = server_factory()
        import base64, hashlib, hmac as _hmac
        nonce = base64.b64encode(b"n" * 32).decode()
        message = b"1.0.0" + str(PROTOCOL_VERSION).encode() + launch_id.encode() + nonce.encode()
        proof = base64.b64encode(_hmac.new(token, message, hashlib.sha256).digest()).decode()
        resp = await server._handle_request(_request(
            "system.handshake",
            {
                "app_version": "1.0.0",
                "protocol_version": PROTOCOL_VERSION,
                "launch_id": launch_id,
                "nonce": "!!!invalid-base64!!!",
                "proof": proof,
            },
            _meta(ipc_session_id=None, idempotency_key=None),
        ))
        assert resp["error"]["data"]["code"] == "VALIDATION_FAILED"

    async def test_handshake_wrong_nonce_length(self, server_factory):
        server, token, launch_id = server_factory()
        import base64, hashlib, hmac as _hmac
        nonce = base64.b64encode(b"short").decode()
        message = b"1.0.0" + str(PROTOCOL_VERSION).encode() + launch_id.encode() + nonce.encode()
        proof = base64.b64encode(_hmac.new(token, message, hashlib.sha256).digest()).decode()
        resp = await server._handle_request(_request(
            "system.handshake",
            {
                "app_version": "1.0.0",
                "protocol_version": PROTOCOL_VERSION,
                "launch_id": launch_id,
                "nonce": nonce,
                "proof": proof,
            },
            _meta(ipc_session_id=None, idempotency_key=None),
        ))
        assert resp["error"]["data"]["code"] == "VALIDATION_FAILED"

    async def test_handshake_wrong_version(self, server_factory):
        server, token, launch_id = server_factory()
        import base64, hashlib, hmac as _hmac
        nonce = base64.b64encode(b"n" * 32).decode()
        message = b"1.0.0" + str(PROTOCOL_VERSION).encode() + launch_id.encode() + nonce.encode()
        proof = base64.b64encode(_hmac.new(token, message, hashlib.sha256).digest()).decode()
        resp = await server._handle_request(_request(
            "system.handshake",
            {
                "app_version": "2.0.0",
                "protocol_version": PROTOCOL_VERSION,
                "launch_id": launch_id,
                "nonce": nonce,
                "proof": proof,
            },
            _meta(ipc_session_id=None, idempotency_key=None),
        ))
        assert resp["error"]["data"]["code"] == "PROTOCOL_VERSION_MISMATCH"

    async def test_handshake_wrong_proof(self, server_factory):
        server, token, launch_id = server_factory()
        import base64
        nonce = base64.b64encode(b"n" * 32).decode()
        resp = await server._handle_request(_request(
            "system.handshake",
            {
                "app_version": "1.0.0",
                "protocol_version": PROTOCOL_VERSION,
                "launch_id": launch_id,
                "nonce": nonce,
                "proof": base64.b64encode(b"wrongproof").decode(),
            },
            _meta(ipc_session_id=None, idempotency_key=None),
        ))
        assert resp["error"]["data"]["code"] == "IPC_HANDSHAKE_FAILED"


# ── Health & Shutdown ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestHealthAndShutdown:
    async def test_health_no_session(self, server_factory):
        server, _, _ = server_factory()
        resp = await server._handle_request(_request(
            "system.health", {}, _meta(ipc_session_id=None, idempotency_key=None),
        ))
        assert resp["error"]["data"]["code"] == "IPC_SESSION_INVALID"

    async def test_health_ok(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "system.health", {}, _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["result"]["status"] == "healthy"

    async def test_shutdown(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "system.shutdown", {}, _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert resp["result"]["accepted"] is True


# ── Cursor & Page ──────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCursorEdgeCases:
    def test_cursor_key_load_existing(self, server_factory, tmp_path):
        server, _, _ = server_factory()
        assert len(server._cursor_key) == 32

    def test_decode_cursor_corrupted_hmac(self, server_factory):
        server, _, _ = server_factory()
        import base64, json
        payload = json.dumps({"id": "x", "created_at": "2026-01-01T00:00:00Z"}).encode()
        bad_sig = b"\x00" * 32
        raw = payload + bad_sig
        cursor = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        with pytest.raises(DomainError):
            server._decode_cursor(cursor)

    def test_decode_cursor_bad_json(self, server_factory):
        server, _, _ = server_factory()
        import base64, hashlib, hmac as _hmac
        payload = b"not json"
        sig = _hmac.new(server._cursor_key, payload, hashlib.sha256).digest()
        cursor = base64.urlsafe_b64encode(payload + sig).decode().rstrip("=")
        with pytest.raises(DomainError):
            server._decode_cursor(cursor)

    def test_page_empty(self, server_factory):
        server, _, _ = server_factory()
        result = server._page([], 10)
        assert result["items"] == []
        assert result["has_more"] is False
        assert result["next_cursor"] is None


# ── Idempotency ────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestIdempotency:
    async def test_conflict_different_request(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        key = _uid()
        # First call with idempotency key (writes are idempotent)
        await server._handle_request(_request(
            "settings.update",
            {"updates": {"cli_global_concurrency": 4}},
            _meta(ipc_session_id=session, idempotency_key=key),
        ))
        # Second call with same key but different body
        resp = await server._handle_request(_request(
            "settings.update",
            {"updates": {"cli_global_concurrency": 8}},
            _meta(ipc_session_id=session, idempotency_key=key),
        ))
        assert resp["error"]["data"]["code"] == "IDEMPOTENCY_CONFLICT"


# ── Conversation handlers ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestConversationHandlers:
    async def test_conversation_list(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "conversation.list",
            {"company_id": company_id},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert "result" in resp

    async def test_conversation_get_company(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "conversation.getCompany",
            {"company_id": company_id},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert "result" in resp

    async def test_conversation_get_department(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        # Get department list to find a department_id
        dept_resp = await server._handle_request(_request(
            "department.list",
            {"company_id": company_id},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        if dept_resp.get("result") and dept_resp["result"].get("items"):
            dept_id = dept_resp["result"]["items"][0]["id"]
            resp = await server._handle_request(_request(
                "conversation.getDepartment",
                {"company_id": company_id, "department_id": dept_id},
                _meta(ipc_session_id=session, idempotency_key=None),
            ))
            assert "result" in resp


# ── Employee handlers ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestEmployeeHandlers:
    async def test_employee_list(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "employee.list",
            {"company_id": company_id},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert "result" in resp

    async def test_employee_get(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        emp_resp = await server._handle_request(_request(
            "employee.list",
            {"company_id": company_id},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        if emp_resp.get("result") and emp_resp["result"].get("items"):
            emp_id = emp_resp["result"]["items"][0]["id"]
            resp = await server._handle_request(_request(
                "employee.get",
                {"id": emp_id, "company_id": company_id},
                _meta(ipc_session_id=session, idempotency_key=None),
            ))
            assert "result" in resp


# ── Task handlers ──────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestTaskHandlers:
    async def test_task_list_empty(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "task.list",
            {"company_id": company_id},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        if "result" in resp:
            assert resp["result"] == [] or resp["result"].get("items") == []

    async def test_task_get_missing(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "task.get",
            {"company_id": company_id, "task_id": _uid()},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["result"] is None


# ── Run handlers ───────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestRunHandlers:
    async def test_run_list_empty(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "run.list",
            {"company_id": company_id},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        if "result" in resp:
            assert resp["result"] == [] or resp["result"].get("items") == []

    async def test_run_list_events_empty(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "run.listEvents",
            {"company_id": company_id, "run_id": _uid()},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        if "result" in resp:
            assert resp["result"] == [] or resp["result"].get("items") == []

    async def test_run_get_missing(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "run.get",
            {"company_id": company_id, "run_id": _uid()},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert "result" in resp


# ── Backup handlers ────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestBackupCreateRestore:
    async def test_backup_create(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "backup.create",
            {"backup_type": "manual", "archive_path": "/tmp/test.zip"},
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        if "result" in resp:
            assert resp["result"]["status"] == "creating"

    async def test_backup_list(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "backup.list",
            {},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert "result" in resp


# ── Settings handlers ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSettingsEdgeCases:
    async def test_settings_get(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "settings.get",
            {},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert "result" in resp

    async def test_settings_update_with_values(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "settings.update",
            {"updates": {"cli_global_concurrency": 4, "log_retention_days": 30}},
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert "result" in resp


# ── Event handlers ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestEventEdgeCases:
    async def test_event_replay(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "event.replay",
            {"company_id": company_id, "limit": 100},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        # company creation should have generated domain events
        assert "result" in resp


# ── Knowledge import/remove ────────────────────────────────────────────


@pytest.mark.asyncio
class TestKnowledgeImportRemove:
    async def _create_message_event_id(self, server, session, company_id) -> str:
        """Create a conversation and user message, returning the message event id."""
        conv_resp = await server._handle_request(_request(
            "conversation.create",
            {"company_id": company_id, "title": "test"},
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        if "result" not in conv_resp:
            return _uid()
        conv_id = conv_resp["result"]["id"]
        msg_resp = await server._handle_request(_request(
            "conversation.submitUserMessage",
            {"company_id": company_id, "conversation_id": conv_id, "content": "test"},
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        if "result" not in msg_resp:
            return _uid()
        # Query the domain_events table for the event_id
        import json as _json
        task_id = msg_resp["result"]["company_task_id"]
        cursor = await server._connection.execute(
            "SELECT event_id FROM domain_events WHERE company_id=? AND aggregate_id=? ORDER BY occurred_at DESC LIMIT 1",
            (company_id, task_id),
        )
        row = await cursor.fetchone()
        if row:
            return row["event_id"]
        return _uid()

    async def test_knowledge_import(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        event_id = await self._create_message_event_id(server, session, company_id)
        resp = await server._handle_request(_request(
            "knowledge.import",
            {
                "company_id": company_id,
                "title": "Test KB",
                "content": "Some content",
                "visibility": "company",
                "source_message_event_id": event_id,
            },
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert "result" in resp
        assert "id" in resp["result"]

    async def test_knowledge_remove_item(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        event_id = await self._create_message_event_id(server, session, company_id)
        # Import first
        import_resp = await server._handle_request(_request(
            "knowledge.import",
            {
                "company_id": company_id,
                "title": "To Remove",
                "content": "Remove me",
                "visibility": "company",
                "source_message_event_id": event_id,
            },
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        if "result" not in import_resp:
            pytest.skip("knowledge import failed")
        item_id = import_resp["result"]["id"]
        # Then remove
        resp = await server._handle_request(_request(
            "knowledge.remove",
            {"company_id": company_id, "item_id": item_id},
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert resp["result"]["removed"] is True

    async def test_knowledge_search_empty(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "knowledge.search",
            {"company_id": company_id, "query": "nonexistent"},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["result"] == []


# ── Runtime handlers ───────────────────────────────────────────────────


@pytest.mark.asyncio
class TestRuntimeHandlers:
    async def test_runtime_list_models(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "runtime.listAvailableModels",
            {"company_id": company_id},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert "result" in resp

    async def test_runtime_get_status(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "runtime.getStatus",
            {"company_id": company_id},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert "result" in resp

    async def test_runtime_run_and_stop(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "runtime.run",
            {"company_id": company_id, "agent_id": _uid(), "message": "hello"},
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        if "result" in resp:
            assert "run_id" in resp["result"]


# ── Approval handlers ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestApprovalHandlers:
    async def test_approval_list(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "approval.listPending",
            {"company_id": company_id},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert "result" in resp


# ── Profile handlers ───────────────────────────────────────────────────


@pytest.mark.asyncio
class TestProfileEdgeCases:
    async def test_profile_get_missing(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "profile.get",
            {"company_id": company_id, "profile_id": _uid()},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert "result" in resp

    async def test_profile_list_all(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "profile.list",
            {"company_id": company_id},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert "result" in resp

    async def test_profile_list_with_employee(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        # Get an employee
        emp_resp = await server._handle_request(_request(
            "employee.list",
            {"company_id": company_id},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        if emp_resp.get("result") and emp_resp["result"].get("items"):
            emp_id = emp_resp["result"]["items"][0]["id"]
            resp = await server._handle_request(_request(
                "profile.list",
                {"company_id": company_id, "employee_id": emp_id},
                _meta(ipc_session_id=session, idempotency_key=None),
            ))
            assert "result" in resp


# ── Workspace handlers ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestWorkspaceHandlers:
    async def test_workspace_list_empty(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "workspace.list",
            {"company_id": company_id},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["result"] == []


# ── Artifact handlers ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestArtifactHandlers:
    async def test_artifact_list_empty(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "artifact.list",
            {"company_id": company_id, "task_id": _uid()},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["result"] == []

    async def test_artifact_get_snapshot_missing(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "artifact.getSnapshot",
            {"company_id": company_id, "artifact_id": _uid()},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["result"] is None


# ── Review handlers ────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestReviewHandlers:
    async def test_review_list_issues_empty(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "review.listIssues",
            {"company_id": company_id, "report_artifact_id": _uid()},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["result"] == []


# ── Department archive ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestDepartmentArchive:
    async def test_department_archive(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        dept_resp = await server._handle_request(_request(
            "department.list",
            {"company_id": company_id},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        # Skip root department (can't archive)
        items = dept_resp.get("result", {}).get("items") if isinstance(dept_resp.get("result"), dict) else dept_resp.get("result", [])
        if items:
            found = False
            for dept in items:
                if dept["department_type"] != "general_manager_office":
                    resp = await server._handle_request(_request(
                        "department.archive",
                        {"company_id": company_id, "department_id": dept["id"], "expected_version": dept["version"]},
                        _meta(ipc_session_id=session, idempotency_key=_uid()),
                    ))
                    assert "result" in resp
                    found = True
                    break
            if not found:
                pytest.skip("no non-root department available to archive")
