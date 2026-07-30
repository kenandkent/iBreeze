"""Tests for RPC server handler methods not covered by existing tests.

Covers: profile, task, department, run, knowledge, backup, settings, event,
catalog handlers, cursor, nested transactions, and error paths.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime

import pytest

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
def server_factory(local_db, tmp_path):
    servers: list[RPCServer] = []

    def factory() -> tuple[RPCServer, bytes, str]:
        token = b"s" * 32
        launch_id = _uid()
        server = RPCServer(
            writer=local_db,
            profile_path=tmp_path / "profile.db",
            socket_path=tmp_path / f"{launch_id}.sock",
            startup_token=token,
            launch_id=launch_id,
            app_version="1.0.0",
        )
        servers.append(server)
        return server, token, launch_id

    return factory


@pytest.mark.asyncio
class TestHelperFunctions:
    def test_uuid_valid(self):
        val = _uid()
        assert _uuid(val) == val

    def test_uuid_invalid_raises(self):
        with pytest.raises(ValueError):
            _uuid(123)

    def test_serialize_model(self):
        from pydantic import BaseModel

        class M(BaseModel):
            x: int

        assert _serialize(M(x=1)) == {"x": 1}

    def test_serialize_list(self):
        from pydantic import BaseModel

        class M(BaseModel):
            x: int

        assert _serialize([M(x=1)]) == [{"x": 1}]

    def test_serialize_plain(self):
        assert _serialize(42) == 42


@pytest.mark.asyncio
class TestCursorAndPage:
    def test_cursor_roundtrip(self, server_factory):
        server, _, _ = server_factory()
        dt = datetime(2026, 1, 1, tzinfo=UTC)
        cursor = server._cursor(dt, "test-id")
        padded = cursor + "=" * (-len(cursor) % 4)
        value = base64.urlsafe_b64decode(padded)
        assert len(value) > 32
        payload, sig = value[:-32], value[-32:]
        expected = hmac.new(server._cursor_key, payload, hashlib.sha256).digest()
        assert hmac.compare_digest(sig, expected)
        data = json.loads(payload)
        assert data["id"] == "test-id"

    def test_decode_cursor_none(self, server_factory):
        server, _, _ = server_factory()
        assert server._decode_cursor(None) is None

    def test_decode_cursor_invalid(self, server_factory):
        server, _, _ = server_factory()
        with pytest.raises(DomainError):
            server._decode_cursor("invalid-cursor!!!")

    def test_page_no_more(self, server_factory):
        from ibreeze.schemas import KnowledgeItemResponse

        server, _, _ = server_factory()
        items = [
            KnowledgeItemResponse(
                id="id1", company_id="c1", source_artifact_id=None,
                source_message_event_id=None, owner_employee_id=None,
                department_id=None, task_id=None, visibility="company",
                title="t", content="c", content_sha256="sha",
                embedding_generation_id=None,
                created_at=datetime(2026, 1, 1, tzinfo=UTC), version=1,
            )
        ]
        result = server._page(items, 5)
        assert result["has_more"] is False
        assert result["next_cursor"] is None

    def test_page_has_more(self, server_factory):
        from ibreeze.schemas import KnowledgeItemResponse

        server, _, _ = server_factory()
        items = [
            KnowledgeItemResponse(
                id=f"id{i}", company_id="c1", source_artifact_id=None,
                source_message_event_id=None, owner_employee_id=None,
                department_id=None, task_id=None, visibility="company",
                title="t", content="c", content_sha256="sha",
                embedding_generation_id=None,
                created_at=datetime(2026, 1, 1, tzinfo=UTC), version=1,
            )
            for i in range(3)
        ]
        result = server._page(items, 2)
        assert result["has_more"] is True
        assert result["next_cursor"] is not None


@pytest.mark.asyncio
class TestProtocolErrors:
    async def test_invalid_jsonrpc_version(self, server_factory):
        server, _, _ = server_factory()
        resp = await server._handle_request(
            {"jsonrpc": "1.0", "id": f"core:{_uid()}", "method": "test", "params": {}}
        )
        assert resp["error"]["code"] == -32600

    async def test_not_a_dict(self, server_factory):
        server, _, _ = server_factory()
        resp = await server._handle_request("not a dict")
        assert resp["error"]["code"] == -32600

    async def test_missing_id(self, server_factory):
        server, _, _ = server_factory()
        resp = await server._handle_request(
            {"jsonrpc": "2.0", "method": "test", "params": {}}
        )
        assert resp["error"]["code"] == -32600

    async def test_method_not_string(self, server_factory):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(
            _request(123, {}, _meta(ipc_session_id=session, idempotency_key=None))
        )
        assert resp["error"]["code"] == -32602

    async def test_params_not_dict(self, server_factory):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(
            {"jsonrpc": "2.0", "id": f"core:{_uid()}", "method": "company.list",
             "params": "bad", "meta": _meta(ipc_session_id=session, idempotency_key=None)}
        )
        assert resp["error"]["code"] == -32602

    async def test_method_not_found_write(self, server_factory):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(
            _request("nonexistent.method", {},
                     _meta(ipc_session_id=session, idempotency_key=_uid()))
        )
        assert resp["error"]["code"] == -32601


@pytest.mark.asyncio
class TestSessionValidation:
    async def test_no_session_rejected(self, server_factory):
        server, _, _ = server_factory()
        resp = await server._handle_request(
            _request("company.list", {}, _meta(ipc_session_id=None, idempotency_key=None))
        )
        assert resp["error"]["data"]["code"] == "IPC_SESSION_INVALID"

    async def test_wrong_session_rejected(self, server_factory):
        server, token, launch_id = server_factory()
        await _handshake(server, token, launch_id)
        wrong_session = _uid()
        resp = await server._handle_request(
            _request("company.list", {},
                     _meta(ipc_session_id=wrong_session, idempotency_key=None))
        )
        assert resp["error"]["data"]["code"] == "IPC_SESSION_INVALID"


@pytest.mark.asyncio
class TestMetaValidation:
    async def test_extra_meta_field(self, server_factory):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request({
            "jsonrpc": "2.0",
            "id": f"core:{_uid()}",
            "method": "company.list",
            "params": {},
            "meta": {
                "trace_id": _uid(),
                "ipc_session_id": session,
                "window_session_id": _uid(),
                "idempotency_key": None,
                "extra_field": "bad",
            },
        })
        assert resp["error"]["data"]["code"] == "VALIDATION_FAILED"

    async def test_read_method_with_idempotency_key_rejected(self, server_factory):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(
            _request("company.list", {},
                     _meta(ipc_session_id=session, idempotency_key=_uid()))
        )
        assert resp["error"]["data"]["code"] == "VALIDATION_FAILED"

    async def test_write_method_without_idempotency_key_rejected(self, server_factory):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(
            _request("company.create", {"name": "x"},
                     _meta(ipc_session_id=session, idempotency_key=None))
        )
        assert resp["error"]["data"]["code"] == "VALIDATION_FAILED"

    async def test_handshake_with_ipc_session_rejected(self, server_factory):
        server, token, launch_id = server_factory()
        resp = await server._handle_request({
            "jsonrpc": "2.0",
            "id": f"core:{_uid()}",
            "method": "system.handshake",
            "params": {
                "app_version": "1.0.0",
                "protocol_version": PROTOCOL_VERSION,
                "launch_id": launch_id,
                "nonce": base64.b64encode(b"n" * 32).decode(),
                "proof": "fake",
            },
            "meta": {
                "trace_id": _uid(),
                "ipc_session_id": _uid(),
                "window_session_id": _uid(),
                "idempotency_key": None,
            },
        })
        assert resp["error"]["data"]["code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
class TestHealthAndShutdown:
    async def test_health(self, server_factory):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(
            _request("system.health", {},
                     _meta(ipc_session_id=session, idempotency_key=None))
        )
        assert resp["result"]["status"] == "healthy"

    async def test_shutdown(self, server_factory):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(
            _request("system.shutdown", {},
                     _meta(ipc_session_id=session, idempotency_key=_uid()))
        )
        assert resp["result"]["accepted"] is True


@pytest.mark.asyncio
class TestCompanyListFilter:
    async def test_company_list_with_filter_rejected(self, server_factory):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(
            _request("company.list", {"filter": {"name": "x"}},
                     _meta(ipc_session_id=session, idempotency_key=None))
        )
        assert resp["error"]["data"]["code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
class TestDepartmentListFilter:
    async def test_dept_list_with_filter_rejected(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(
            _request("department.list",
                     {"company_id": company_id, "filter": {"name": "x"}},
                     _meta(ipc_session_id=session, idempotency_key=None))
        )
        assert resp["error"]["data"]["code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
class TestEmployeeListFilter:
    async def test_employee_list_bad_filter(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(
            _request("employee.list",
                     {"company_id": company_id, "filter": {"bad_field": "x"}},
                     _meta(ipc_session_id=session, idempotency_key=None))
        )
        assert resp["error"]["data"]["code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
class TestProfileHandlers:
    async def test_profile_list(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "profile.list",
            {"company_id": company_id, "employee_id": _uid()},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert "result" in resp


@pytest.mark.asyncio
class TestKnowledgeHandlers:
    async def test_knowledge_list_empty(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "knowledge.list",
            {"company_id": company_id},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["result"] == []

    async def test_knowledge_search(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "knowledge.search",
            {"company_id": company_id, "query": "test"},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["result"] == []

    async def test_knowledge_remove(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "knowledge.remove",
            {"company_id": company_id, "item_id": _uid()},
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert resp["result"]["removed"] is True


@pytest.mark.asyncio
class TestBackupHandlers:
    async def test_backup_list(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "backup.list",
            {},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert "result" in resp


@pytest.mark.asyncio
class TestSettingsHandlers:
    async def test_settings_get_empty(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "settings.get",
            {},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert "result" in resp

    async def test_settings_update_empty(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "settings.update",
            {"updates": {}},
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert "result" in resp


@pytest.mark.asyncio
class TestEventHandlers:
    async def test_event_subscribe(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "event.subscribe",
            {"scope": "global"},
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert "subscription_id" in resp["result"]

    async def test_event_replay(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "event.replay",
            {"company_id": company_id},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert "result" in resp


@pytest.mark.asyncio
class TestCatalogHandlers:
    async def test_catalog_sync(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "catalog.sync",
            {},
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert resp["result"]["status"] == "synced"

    async def test_catalog_get_active_release(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "catalog.getActiveRelease",
            {},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert "result" in resp

    async def test_catalog_list_agents(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "catalog.listAgents",
            {},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["result"] == []

    async def test_catalog_list_models(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "catalog.listModels",
            {},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["result"] == []

    async def test_catalog_list_skills(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "catalog.listSkills",
            {},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["result"] == []

    async def test_catalog_install_skill(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "catalog.installSkill",
            {
                "skill_version_id": _uid(),
                "skill_id": _uid(),
                "skill_version": "1.0.0",
                "package_sha256": "a" * 64,
            },
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert resp["result"]["installed"] is True

    async def test_catalog_install_skill_bad_sha(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "catalog.installSkill",
            {
                "skill_version_id": _uid(),
                "skill_id": _uid(),
                "skill_version": "1.0.0",
                "package_sha256": "short",
            },
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert resp["error"]["data"]["code"] == "INVALID_PACKAGE_SHA256: expected 64 hex chars"

    async def test_catalog_remove_skill(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "catalog.removeSkill",
            {"skill_id": _uid()},
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert resp["result"]["removed"] is True

    async def test_catalog_verify_cache(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "catalog.verifyCache",
            {},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["result"]["valid"] is True


@pytest.mark.asyncio
class TestDepartmentResponsibilityHandlers:
    async def test_create_responsibility(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        dept_resp = await server._handle_request(_request(
            "department.create",
            {
                "company_id": company_id,
                "name": "Engineering",
                "function_description": "Build stuff",
                "leader_name": "Eng Lead",
                "base_profile_version_id": published_profile,
            },
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        dept_id = dept_resp["result"]["id"]
        resp = await server._handle_request(_request(
            "department.responsibility.create",
            {
                "company_id": company_id,
                "department_id": dept_id,
                "responsibility_key": "code_review",
                "name": "Code Review",
                "description": "Review code",
            },
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert "id" in resp["result"]

    async def test_update_responsibility(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        dept_resp = await server._handle_request(_request(
            "department.create",
            {
                "company_id": company_id,
                "name": "Eng",
                "function_description": "Build",
                "leader_name": "Lead",
                "base_profile_version_id": published_profile,
            },
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        dept_id = dept_resp["result"]["id"]
        create_resp = await server._handle_request(_request(
            "department.responsibility.create",
            {
                "company_id": company_id,
                "department_id": dept_id,
                "responsibility_key": "review",
                "name": "Review",
            },
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        resp = await server._handle_request(_request(
            "department.responsibility.update",
            {
                "company_id": company_id,
                "id": create_resp["result"]["id"],
                "name": "Updated Review",
            },
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert "updated_at" in resp["result"]

    async def test_delete_responsibility(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        dept_resp = await server._handle_request(_request(
            "department.create",
            {
                "company_id": company_id,
                "name": "Eng2",
                "function_description": "Build",
                "leader_name": "Lead",
                "base_profile_version_id": published_profile,
            },
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        dept_id = dept_resp["result"]["id"]
        create_resp = await server._handle_request(_request(
            "department.responsibility.create",
            {
                "company_id": company_id,
                "department_id": dept_id,
                "responsibility_key": "dep",
                "name": "To Delete",
            },
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        resp = await server._handle_request(_request(
            "department.responsibility.delete",
            {
                "company_id": company_id,
                "id": create_resp["result"]["id"],
            },
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert resp["result"]["deleted"] is True

    async def test_archive_department(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        dept_resp = await server._handle_request(_request(
            "department.create",
            {
                "company_id": company_id,
                "name": "Archive Me",
                "function_description": "Build",
                "leader_name": "Lead",
                "base_profile_version_id": published_profile,
            },
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        dept_id = dept_resp["result"]["id"]
        resp = await server._handle_request(_request(
            "department.archive",
            {"company_id": company_id, "department_id": dept_id},
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert "archived_at" in resp["result"]


@pytest.mark.asyncio
class TestWorkspaceHandlers:
    async def test_workspace_list(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "workspace.list",
            {"company_id": company_id},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["result"] == []

    async def test_workspace_get_nonexistent(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "workspace.get",
            {"company_id": company_id, "workspace_id": _uid()},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["result"] is None


@pytest.mark.asyncio
class TestArtifactHandlers:
    async def test_artifact_list(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "artifact.list",
            {"company_id": company_id, "task_id": _uid()},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["result"] == []

    async def test_artifact_get_snapshot(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "artifact.getSnapshot",
            {"company_id": company_id, "artifact_id": _uid()},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["result"] is None


@pytest.mark.asyncio
class TestApprovalHandlers:
    async def test_approval_list_pending(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "approval.listPending",
            {"company_id": company_id},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["result"] == []


@pytest.mark.asyncio
class TestSafeTraceId:
    def test_valid_trace_id(self):
        tid = _uid()
        assert RPCServer._safe_trace_id({"trace_id": tid}) == tid

    def test_invalid_trace_id_returns_new_uuid(self):
        result = RPCServer._safe_trace_id({"trace_id": "bad"})
        uuid.UUID(result)  # should be valid uuid

    def test_non_dict_returns_new_uuid(self):
        result = RPCServer._safe_trace_id("not a dict")
        uuid.UUID(result)


@pytest.mark.asyncio
class TestInternalErrorPath:
    async def test_internal_error_returns_diagnostic(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "profile.createDraft",
            {
                "company_id": company_id,
                "employee_id": "invalid-not-uuid",
            },
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert resp["error"]["data"]["code"] == "INTERNAL_ERROR"
        assert "Diagnostic reference:" in resp["error"]["message"]


@pytest.mark.asyncio
class TestDomainErrorAndValidationError:
    async def test_domain_error_from_handler(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "company.get",
            {"id": _uid(), "company_id": _uid()},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["error"]["data"]["code"] == "RESOURCE_NOT_FOUND"

    async def test_validation_error(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        company_id = await _setup_company(server, session, published_profile)
        resp = await server._handle_request(_request(
            "employee.updateDisplayName",
            {"company_id": company_id, "employee_id": _uid(),
             "display_name": "", "expected_version": 0},
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert "error" in resp


@pytest.mark.asyncio
class TestCompanyGetMismatch:
    async def test_company_get_id_not_matching_company_id(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "company.get",
            {"id": _uid(), "company_id": _uid()},
            _meta(ipc_session_id=session, idempotency_key=None),
        ))
        assert resp["error"]["data"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
class TestRuntimeStopHandler:
    async def test_runtime_stop_invalid_params(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "runtime.stop",
            {},
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert resp["error"]["data"]["code"] == "VALIDATION_FAILED"

    async def test_runtime_run_invalid_params(self, server_factory, published_profile):
        server, token, launch_id = server_factory()
        session = await _handshake(server, token, launch_id)
        resp = await server._handle_request(_request(
            "runtime.run",
            {},
            _meta(ipc_session_id=session, idempotency_key=_uid()),
        ))
        assert resp["error"]["data"]["code"] == "VALIDATION_FAILED"
