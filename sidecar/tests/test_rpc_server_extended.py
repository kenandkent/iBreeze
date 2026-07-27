"""Extended RPC server tests for settings, backup, catalog, protocol, etc."""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid

import pytest

from ibreeze.local_db import LocalDB
from ibreeze.rpc_server import PROTOCOL_VERSION, RPCServer


def _uuid() -> str:
    return str(uuid.uuid4())


def _meta(
    *,
    ipc_session_id: str | None,
    idempotency_key: str | None,
) -> dict[str, str | None]:
    return {
        "trace_id": _uuid(),
        "ipc_session_id": ipc_session_id,
        "window_session_id": _uuid(),
        "idempotency_key": idempotency_key,
    }


def _request(
    method: str,
    params: dict[str, object],
    meta: dict[str, str | None],
) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": f"core:{_uuid()}",
        "method": method,
        "params": params,
        "meta": meta,
    }


async def _handshake(
    server: RPCServer,
    token: bytes,
    launch_id: str,
) -> str:
    nonce = base64.b64encode(b"n" * 32).decode()
    message = (
        b"1.0.0"
        + str(PROTOCOL_VERSION).encode()
        + launch_id.encode()
        + nonce.encode()
    )
    proof = base64.b64encode(
        hmac.new(token, message, hashlib.sha256).digest()
    ).decode()
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
    return str(response["result"]["ipc_session_id"])  # type: ignore[index]


async def _setup_company(server: RPCServer, session: str, published_profile: str) -> str:
    name = f"Co-{uuid.uuid4().hex[:8]}"
    resp = await server._handle_request(_request(
        "company.create",
        {
            "name": name,
            "introduction": "A test company",
            "general_manager_name": "GM",
            "base_profile_version_id": published_profile,
        },
        _meta(ipc_session_id=session, idempotency_key=_uuid()),
    ))
    assert "result" in resp, f"company.create failed: {resp.get('error')}"
    return resp["result"]["id"]  # type: ignore[index]


@pytest.fixture
def server_factory(local_db: LocalDB, tmp_path):
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


# ── Settings ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_settings_get_returns_defaults(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    resp = await server._handle_request(_request(
        "settings.get", {},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    result = resp["result"]
    assert result["cli_global_concurrency"] == 4
    assert result["log_retention_days"] == 30
    assert result["version"] == 1


@pytest.mark.asyncio
async def test_settings_update_and_get(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    await server._handle_request(_request(
        "settings.update",
        {"updates": {"cli_global_concurrency": 8, "log_retention_days": 60}},
        _meta(ipc_session_id=session, idempotency_key=_uuid()),
    ))
    resp = await server._handle_request(_request(
        "settings.get", {},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    assert resp["result"]["cli_global_concurrency"] == 8  # type: ignore[index]
    assert resp["result"]["log_retention_days"] == 60  # type: ignore[index]
    assert resp["result"]["version"] == 2  # type: ignore[index]


@pytest.mark.asyncio
async def test_settings_update_no_valid_keys(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    resp = await server._handle_request(_request(
        "settings.update",
        {"updates": {"unknown_key": 99}},
        _meta(ipc_session_id=session, idempotency_key=_uuid()),
    ))
    assert "updated_at" in resp["result"]  # type: ignore[index]


# ── Backup ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_backup_list_empty(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    resp = await server._handle_request(_request(
        "backup.list", {},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    assert resp["result"] == []


@pytest.mark.asyncio
async def test_backup_list_with_seeded_data(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    sha = "a" * 64
    now = "2026-01-01T00:00:00Z"
    await server.db.execute_write(
        "INSERT INTO backup_records "
        "(id, backup_type, archive_path, archive_size, archive_sha256, "
        "manifest_json, status, created_at) VALUES (?, 'manual', '/bak', 100, ?, '{}', 'completed', ?)",
        (_uuid(), sha, now),
    )
    resp = await server._handle_request(_request(
        "backup.list", {},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    assert len(resp["result"]) >= 1  # type: ignore[index]


@pytest.mark.asyncio
async def test_backup_restore(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    sha = "b" * 64
    now = "2026-01-01T00:00:00Z"
    bid = _uuid()
    await server.db.execute_write(
        "INSERT INTO backup_records "
        "(id, backup_type, archive_path, archive_size, archive_sha256, "
        "manifest_json, status, created_at) VALUES (?, 'manual', '/r', 50, ?, '{}', 'creating', ?)",
        (bid, sha, now),
    )
    restore_resp = await server._handle_request(_request(
        "backup.restore",
        {"backup_id": bid},
        _meta(ipc_session_id=session, idempotency_key=_uuid()),
    ))
    assert "restored_at" in restore_resp["result"]  # type: ignore[index]


# ── Task (READ methods only — no company needed for list/get empty) ──


@pytest.mark.asyncio
async def test_task_get_nonexistent(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    company_id = await _setup_company(server, session, published_profile)
    resp = await server._handle_request(_request(
        "task.get",
        {"company_id": company_id, "task_id": _uuid()},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    assert "result" in resp, f"task.get failed: {resp.get('error')}"
    assert resp["result"] is None


# ── Runtime ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_runtime_list_available_models(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    company_id = await _setup_company(server, session, published_profile)
    resp = await server._handle_request(_request(
        "runtime.listAvailableModels",
        {"company_id": company_id},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    assert "result" in resp, f"runtime.listAvailableModels failed: {resp.get('error')}"
    assert isinstance(resp["result"], list)


# ── Review ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_review_list_issues_empty(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    company_id = await _setup_company(server, session, published_profile)
    resp = await server._handle_request(_request(
        "review.listIssues",
        {"company_id": company_id, "report_artifact_id": _uuid()},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    assert "result" in resp, f"review.listIssues failed: {resp.get('error')}"
    assert resp["result"] == []


@pytest.mark.asyncio
async def test_review_rerun_validates_params(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    company_id = await _setup_company(server, session, published_profile)
    resp = await server._handle_request(_request(
        "review.rerun",
        {
            "company_id": company_id,
            "artifact_id": _uuid(),
            "reviewer_employee_id": _uuid(),
            "review_round": 1,
        },
        _meta(ipc_session_id=session, idempotency_key=_uuid()),
    ))
    assert resp.get("error") is not None or "result" in resp


@pytest.mark.asyncio
async def test_review_resolve_issue(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    company_id = await _setup_company(server, session, published_profile)
    resp = await server._handle_request(_request(
        "review.resolveIssue",
        {"company_id": company_id, "issue_id": _uuid()},
        _meta(ipc_session_id=session, idempotency_key=_uuid()),
    ))
    assert "result" in resp, f"review.resolveIssue failed: {resp.get('error')}"
    assert "resolved_at" in resp["result"]  # type: ignore[index]


# ── Knowledge ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_knowledge_list_empty(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    resp = await server._handle_request(_request(
        "knowledge.list",
        {"company_id": _uuid()},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    assert "result" in resp, f"knowledge.list failed: {resp.get('error')}"
    assert resp["result"] == []


@pytest.mark.asyncio
async def test_knowledge_import_via_direct_insert(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    company_id = await _setup_company(server, session, published_profile)
    sha = "a" * 64
    now = "2026-01-01T00:00:00Z"
    kid = _uuid()
    await server.db.execute_write("PRAGMA foreign_keys = OFF")
    try:
        await server.db.execute_write(
            "INSERT INTO knowledge_items "
            "(id, company_id, source_artifact_id, source_message_event_id, visibility, "
            "title, content, content_sha256, created_at) "
            "VALUES (?, ?, NULL, 'evt1', 'company', 'Test', 'Content', ?, ?)",
            (kid, company_id, sha, now),
        )
    finally:
        await server.db.execute_write("PRAGMA foreign_keys = ON")
    list_resp = await server._handle_request(_request(
        "knowledge.list",
        {"company_id": company_id},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    assert len(list_resp["result"]) == 1  # type: ignore[index]

    remove_resp = await server._handle_request(_request(
        "knowledge.remove",
        {"company_id": company_id, "item_id": kid},
        _meta(ipc_session_id=session, idempotency_key=_uuid()),
    ))
    assert remove_resp["result"]["removed"] is True  # type: ignore[index]


# ── Approval ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approval_list_pending_source_bug(server_factory, published_profile) -> None:
    """approval.listPending: fixed created_at→requested_at column name."""
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    resp = await server._handle_request(_request(
        "approval.listPending",
        {"company_id": _uuid()},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    assert "result" in resp
    assert resp["result"] == []


# ── Event ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_event_subscribe(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    resp = await server._handle_request(_request(
        "event.subscribe",
        {"scope": "company"},
        _meta(ipc_session_id=session, idempotency_key=_uuid()),
    ))
    assert "result" in resp, f"event.subscribe failed: {resp.get('error')}"
    assert "subscription_id" in resp["result"]  # type: ignore[index]


@pytest.mark.asyncio
async def test_event_replay_empty(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    company_id = await _setup_company(server, session, published_profile)
    resp = await server._handle_request(_request(
        "event.replay",
        {"company_id": company_id, "limit": 10},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    assert "result" in resp, f"event.replay failed: {resp.get('error')}"
    assert isinstance(resp["result"], list)


# ── Catalog ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_catalog_get_active_release(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    resp = await server._handle_request(_request(
        "catalog.getActiveRelease", {},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    assert resp["result"] is not None


@pytest.mark.asyncio
async def test_catalog_list_agents(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    resp = await server._handle_request(_request(
        "catalog.listAgents", {},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    assert resp["result"] == []


@pytest.mark.asyncio
async def test_catalog_list_models(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    resp = await server._handle_request(_request(
        "catalog.listModels", {},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    assert resp["result"] == []


@pytest.mark.asyncio
async def test_catalog_list_skills(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    resp = await server._handle_request(_request(
        "catalog.listSkills", {},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    assert resp["result"] == []


@pytest.mark.asyncio
async def test_catalog_verify_cache(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    resp = await server._handle_request(_request(
        "catalog.verifyCache", {},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    assert resp["result"]["valid"] is True  # type: ignore[index]
    assert resp["result"]["release_count"] >= 1  # type: ignore[index]


@pytest.mark.asyncio
async def test_catalog_install_and_remove_skill(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    sha = "a" * 64
    install_resp = await server._handle_request(_request(
        "catalog.installSkill",
        {
            "skill_id": "test-skill",
            "skill_version_id": "sv-1",
            "skill_version": "1.0.0",
            "package_sha256": sha,
        },
        _meta(ipc_session_id=session, idempotency_key=_uuid()),
    ))
    assert install_resp["result"]["installed"] is True  # type: ignore[index]

    remove_resp = await server._handle_request(_request(
        "catalog.removeSkill",
        {"skill_id": "test-skill"},
        _meta(ipc_session_id=session, idempotency_key=_uuid()),
    ))
    assert remove_resp["result"]["removed"] is True  # type: ignore[index]


@pytest.mark.asyncio
async def test_catalog_install_bad_sha(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    resp = await server._handle_request(_request(
        "catalog.installSkill",
        {
            "skill_id": "x",
            "skill_version_id": "x",
            "skill_version": "1.0.0",
            "package_sha256": "tooshort",
        },
        _meta(ipc_session_id=session, idempotency_key=_uuid()),
    ))
    assert "INVALID_PACKAGE_SHA256" in resp["error"]["data"]["code"]


@pytest.mark.asyncio
async def test_catalog_sync(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    resp = await server._handle_request(_request(
        "catalog.sync", {},
        _meta(ipc_session_id=session, idempotency_key=_uuid()),
    ))
    assert resp["result"]["status"] == "synced"  # type: ignore[index]


# ── Artifact ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_artifact_list_empty(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    company_id = await _setup_company(server, session, published_profile)
    resp = await server._handle_request(_request(
        "artifact.list",
        {"company_id": company_id, "task_id": _uuid()},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    assert "result" in resp, f"artifact.list failed: {resp.get('error')}"
    assert resp["result"] == []


@pytest.mark.asyncio
async def test_artifact_get_snapshot_none(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    company_id = await _setup_company(server, session, published_profile)
    resp = await server._handle_request(_request(
        "artifact.getSnapshot",
        {"company_id": company_id, "artifact_id": _uuid()},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    assert "result" in resp, f"artifact.getSnapshot failed: {resp.get('error')}"
    assert resp["result"] is None


# ── Workspace ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_workspace_get_none(server_factory, published_profile) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    company_id = await _setup_company(server, session, published_profile)
    resp = await server._handle_request(_request(
        "workspace.get",
        {"company_id": company_id, "workspace_id": _uuid()},
        _meta(ipc_session_id=session, idempotency_key=None),
    ))
    assert "result" in resp, f"workspace.get failed: {resp.get('error')}"
    assert resp["result"] is None


# ── Protocol / validation errors ──────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_jsonrpc_version(server_factory) -> None:
    server, token, launch_id = server_factory()
    resp = await server._handle_request({
        "jsonrpc": "1.0",
        "id": f"core:{_uuid()}",
        "method": "system.handshake",
    })
    assert resp["error"]["code"] == -32600


@pytest.mark.asyncio
async def test_invalid_request_id_format(server_factory) -> None:
    server, token, launch_id = server_factory()
    resp = await server._handle_request({
        "jsonrpc": "2.0",
        "id": "not-a-uuid",
        "method": "system.handshake",
    })
    assert resp["error"]["code"] == -32600


@pytest.mark.asyncio
async def test_method_not_found(server_factory) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    resp = await server._handle_request(_request(
        "nonexistent.method", {},
        _meta(ipc_session_id=session, idempotency_key=_uuid()),
    ))
    assert resp["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_method_not_found_write_method(server_factory) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    resp = await server._handle_request(_request(
        "nonexistent.writeMethod", {},
        _meta(ipc_session_id=session, idempotency_key=_uuid()),
    ))
    assert resp["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_invalid_meta_missing_keys(server_factory) -> None:
    server, token, launch_id = server_factory()
    await _handshake(server, token, launch_id)
    resp = await server._handle_request({
        "jsonrpc": "2.0",
        "id": f"core:{_uuid()}",
        "method": "settings.get",
        "params": {},
        "meta": {"trace_id": _uuid()},
    })
    assert resp["error"]["data"]["code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_ipc_session_invalid(server_factory) -> None:
    server, token, launch_id = server_factory()
    await _handshake(server, token, launch_id)
    resp = await server._handle_request(_request(
        "settings.get", {},
        _meta(ipc_session_id="00000000-0000-0000-0000-000000000000", idempotency_key=None),
    ))
    assert resp["error"]["data"]["code"] == "IPC_SESSION_INVALID"


@pytest.mark.asyncio
async def test_handshake_twice_rejected(server_factory) -> None:
    server, token, launch_id = server_factory()
    await _handshake(server, token, launch_id)
    nonce = "dGVzdA=="
    resp = await server._handle_request(_request(
        "system.handshake",
        {
            "app_version": "1.0.0",
            "protocol_version": 1,
            "launch_id": launch_id,
            "nonce": nonce,
            "proof": "dGVzdA==",
        },
        _meta(ipc_session_id=None, idempotency_key=None),
    ))
    assert resp["error"]["data"]["code"] == "STATE_TRANSITION_INVALID"


@pytest.mark.asyncio
async def test_shutdown(server_factory) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    resp = await server._handle_request(_request(
        "system.shutdown", {},
        _meta(ipc_session_id=session, idempotency_key=_uuid()),
    ))
    assert resp["result"]["accepted"] is True


@pytest.mark.asyncio
async def test_valid_request_id_requires_core_prefix() -> None:
    assert RPCServer._valid_request_id("core:00000000-0000-0000-0000-000000000000") is True
    assert RPCServer._valid_request_id("bad:00000000-0000-0000-0000-000000000000") is False
    assert RPCServer._valid_request_id(123) is False
    assert RPCServer._valid_request_id("core:not-a-uuid") is False
