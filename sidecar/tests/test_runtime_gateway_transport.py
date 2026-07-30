"""Tests for runtime/gateway.py, runtime/transport.py, runtime/event_normalizer.py gaps."""

from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from ibreeze.runtime.event_normalizer import (
    EVENT_TYPES,
    create_approval_event,
    create_checkpoint,
    create_compacted_event,
    create_model_delta,
    create_model_done,
    create_run_cancelled,
    create_run_completed,
    create_run_failed,
    create_run_started,
    create_tool_approved_event,
    create_tool_event,
    create_tool_rejected_event,
    create_verification_completed_event,
    create_verification_started_event,
    create_workspace_changed_event,
    normalize_event,
    store_event,
)
from ibreeze.runtime.gateway import (
    RunNotFoundError,
    RunValidationError,
    cancel,
    get_status,
    resume,
    start,
)
from ibreeze.runtime.model_loop import ModelTurn
from ibreeze.runtime.transport import (
    MAX_FRAME_BYTES,
    ReverseRpcClient,
    ReverseRpcTransport,
    UdsConnection,
    UsageStats,
    _encode_frame,
    _read_frame,
    create_transport,
    get_reverse_rpc_socket_path,
    mark_sidecar_own_socket,
    set_reverse_rpc_socket_path,
)


def _sha256(data: str) -> str:
    import hashlib
    return hashlib.sha256(data.encode()).hexdigest()


async def _setup_gateway_env(db: aiosqlite.Connection, company_id: str) -> None:
    now = "2026-01-01T00:00:00Z"
    rev_id = str(uuid.uuid4())
    dept_rev_id = str(uuid.uuid4())
    conv_id = str(uuid.uuid4())
    dept_conv_id = str(uuid.uuid4())
    dept_id = str(uuid.uuid4())
    employee_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    profile_id = str(uuid.uuid4())
    release_id = str(uuid.uuid4())
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """INSERT INTO company_revisions
               (id, company_id, revision_number, name, introduction, content_sha256,
                created_by_type, created_at)
               VALUES (?, ?, 1, 'Co', 'Intro', ?, 'system', ?)""",
            (rev_id, company_id, _sha256("co"), now),
        )
        await db.execute(
            """INSERT INTO conversations (id, company_id, conversation_type, status, created_at)
               VALUES (?, ?, 'department', 'active', ?)""",
            (dept_conv_id, company_id, now),
        )
        await db.execute(
            """INSERT INTO department_revisions
               (id, department_id, company_id, revision_number, name,
                function_description, content_sha256, created_at)
               VALUES (?, ?, ?, 1, 'Root', 'Root', ?, ?)""",
            (dept_rev_id, dept_id, company_id, _sha256("root"), now),
        )
        await db.execute(
            """INSERT INTO employees (id, company_id, department_id, display_name, normalized_display_name,
                base_profile_version_id, workflow_role, status, created_at, updated_at, version)
               VALUES (?, ?, ?, 'GM', 'gm', ?, 'general_manager', 'active', ?, ?, 1)""",
            (employee_id, company_id, dept_id, version_id, now, now),
        )
        await db.execute(
            """INSERT INTO departments (id, company_id, department_type, normalized_name, current_revision_id,
                leader_employee_id, department_conversation_id, status, created_at, updated_at, version)
               VALUES (?, ?, 'general_manager_office', 'root', ?, ?, ?, 'active', ?, ?, 1)""",
            (dept_id, company_id, dept_rev_id, employee_id, dept_conv_id, now, now),
        )
        await db.execute(
            """INSERT INTO conversations (id, company_id, conversation_type, status, created_at)
               VALUES (?, ?, 'company', 'active', ?)""",
            (conv_id, company_id, now),
        )
        await db.execute(
            """INSERT INTO companies (id, normalized_name, current_revision_id, general_manager_office_id,
                general_manager_employee_id, company_conversation_id, status, created_at, updated_at, version)
               VALUES (?, 't', ?, ?, ?, ?, 'active', ?, ?, 1)""",
                (company_id, rev_id, dept_id, employee_id, conv_id, now, now),
        )
        await db.execute(
            """INSERT INTO catalog_cache_releases (release_id, release_sequence, manifest_json, manifest_sha256,
                signature, signing_key_id, status, downloaded_at, activated_at)
               VALUES (?, 1, '{}', ?, 'sig', 'key', 'active', ?, ?)""",
            (release_id, _sha256("{}"), now, now),
        )
        await db.execute(
            """INSERT INTO employee_base_profiles (id, company_id, name, normalized_name, description,
                current_version_id, status, created_at, updated_at, version)
               VALUES (?, ?, 'Default', 'default', 'Default', ?, 'active', ?, ?, 1)""",
            (profile_id, company_id, version_id, now, now),
        )
        await db.execute(
            """INSERT INTO employee_base_profile_versions
               (id, profile_id, version_number, name, description, profile_type,
                runtime_binding_json, system_prompt, capability_tags_json,
                tool_policy_json, timeout_seconds, max_retries, workspace_policy,
                catalog_release_id, content_sha256, status, created_at, published_at)
               VALUES (?, ?, 1, 'Default v1', 'Default', 'agent_cli', '{"adapter_type":"codex_cli"}',
                       'Act.', '[]', '{}', 300, 2, 'workspace_rw_external_ro', ?, ?,
                       'published', ?, ?)""",
            (version_id, profile_id, release_id, _sha256("v1"), now, now),
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()


async def _create_task(db: aiosqlite.Connection, company_id: str, task_id: str) -> None:
    now = "2026-01-01T00:00:00Z"
    conv_id = str(uuid.uuid4())
    msg_event = str(uuid.uuid4())
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """INSERT OR IGNORE INTO company_tasks
               (id, company_id, supersedes_task_id, company_conversation_id, user_message_event_id,
                title, status, created_at, updated_at, version)
               VALUES (?, ?, NULL, ?, ?, 'Task', 'draft', ?, ?, 1)""",
            (task_id, company_id, conv_id, msg_event, now, now),
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()


async def _create_run(
    db: aiosqlite.Connection, company_id: str, run_id: str, task_id: str,
    employee_id: str, conv_id: str, status: str = "queued",
    resume_state: str | None = None,
) -> None:
    now = "2026-01-01T00:00:00Z"
    sha = _sha256("spec")
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """INSERT INTO agent_runs
               (id, company_id, company_task_id, work_item_id, employee_id,
                conversation_id, availability_snapshot_id, execution_snapshot_id,
                run_purpose, adapter_type, run_spec_json, run_spec_sha256,
                status, resume_state, attempt, created_at, updated_at, version)
               VALUES (?, ?, ?, ?, ?, ?, 'avail', 'exec', 'review', 'codex_cli', '{}', ?,
                       ?, ?, 1, ?, ?, 1)""",
            (run_id, company_id, task_id, task_id, employee_id, conv_id,
             sha, status, resume_state, now, now),
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()


@pytest.fixture
async def gw_env(db: aiosqlite.Connection):
    company_id = str(uuid.uuid4())
    await _setup_gateway_env(db, company_id)
    emp_row = await (await db.execute(
        "SELECT id FROM employees WHERE company_id=?", (company_id,)
    )).fetchone()
    conv_row = await (await db.execute(
        "SELECT id FROM conversations WHERE company_id=? AND conversation_type='company'", (company_id,)
    )).fetchone()
    return {
        "company_id": company_id,
        "employee_id": emp_row["id"],
        "conv_id": conv_row["id"],
    }


# ── gateway ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
class TestGatewayStart:
    async def test_start_success(self, db, gw_env):
        company_id = gw_env["company_id"]
        task_id = str(uuid.uuid4())
        await _create_task(db, company_id, task_id)
        result = await start(
            db,
            company_id=company_id,
            company_task_id=task_id,
            employee_id=gw_env["employee_id"],
            model_id="gpt-4o",
            prompt="Build something",
            run_purpose="company_plan",
            adapter_type="codex_cli",
            conversation_id=gw_env["conv_id"],
            availability_snapshot_id="avail-1",
            execution_snapshot_id="exec-1",
        )
        assert result["status"] == "queued"
        assert result["run_id"]

    async def test_start_nonexistent_task(self, db, gw_env):
        with pytest.raises(RunNotFoundError):
            await start(
                db,
                company_id=gw_env["company_id"],
                company_task_id="nonexistent",
                employee_id=gw_env["employee_id"],
                model_id="gpt-4o", prompt="test",
                run_purpose="company_plan", adapter_type="codex_cli",
                conversation_id=gw_env["conv_id"],
                availability_snapshot_id="a", execution_snapshot_id="e",
            )

    async def test_start_nonexistent_employee(self, db, gw_env):
        company_id = gw_env["company_id"]
        task_id = str(uuid.uuid4())
        await _create_task(db, company_id, task_id)
        with pytest.raises(RunNotFoundError):
            await start(
                db, company_id=company_id, company_task_id=task_id,
                employee_id="nonexistent", model_id="gpt-4o", prompt="test",
                run_purpose="company_plan", adapter_type="codex_cli",
                conversation_id=gw_env["conv_id"],
                availability_snapshot_id="a", execution_snapshot_id="e",
            )


@pytest.mark.asyncio
class TestGatewayCancel:
    async def test_cancel_success(self, db, gw_env):
        company_id = gw_env["company_id"]
        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        await _create_task(db, company_id, task_id)
        await _create_run(db, company_id, run_id, task_id, gw_env["employee_id"], gw_env["conv_id"], "running")
        result = await cancel(db, company_id, run_id, reason="test cancel")
        assert result["status"] == "cancelled"

    async def test_cancel_terminal(self, db, gw_env):
        company_id = gw_env["company_id"]
        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        await _create_task(db, company_id, task_id)
        await _create_run(db, company_id, run_id, task_id, gw_env["employee_id"], gw_env["conv_id"], "succeeded")
        result = await cancel(db, company_id, run_id)
        assert result["status"] == "succeeded"

    async def test_cancel_nonexistent(self, db, gw_env):
        with pytest.raises(RunNotFoundError):
            await cancel(db, gw_env["company_id"], "nonexistent")


@pytest.mark.asyncio
class TestGatewayResume:
    async def test_resume_waiting_approval(self, db, gw_env):
        company_id = gw_env["company_id"]
        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        await _create_task(db, company_id, task_id)
        await _create_run(db, company_id, run_id, task_id, gw_env["employee_id"], gw_env["conv_id"],
                          "waiting_approval", resume_state="running")
        result = await resume(db, company_id, run_id)
        assert result["status"] == "running"

    async def test_resume_non_waiting(self, db, gw_env):
        company_id = gw_env["company_id"]
        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        await _create_task(db, company_id, task_id)
        await _create_run(db, company_id, run_id, task_id, gw_env["employee_id"], gw_env["conv_id"], "running")
        with pytest.raises(RunValidationError, match="STATE_TRANSITION_INVALID"):
            await resume(db, company_id, run_id)

    async def test_resume_nonexistent(self, db, gw_env):
        with pytest.raises(RunNotFoundError):
            await resume(db, gw_env["company_id"], "nonexistent")


@pytest.mark.asyncio
class TestGatewayGetStatus:
    async def test_get_status(self, db, gw_env):
        company_id = gw_env["company_id"]
        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        await _create_task(db, company_id, task_id)
        await _create_run(db, company_id, run_id, task_id, gw_env["employee_id"], gw_env["conv_id"])
        status = await get_status(db, company_id, run_id)
        assert status["id"] == run_id

    async def test_get_status_nonexistent(self, db, gw_env):
        with pytest.raises(RunNotFoundError):
            await get_status(db, gw_env["company_id"], "nonexistent")


# ── transport ────────────────────────────────────────────────────────
class TestTransport:
    def test_reverse_rpc_transport_init(self):
        t = ReverseRpcTransport(credential_ref="cred-abc", model="gpt-4o")
        assert t._credential_ref == "cred-abc"
        assert t._model == "gpt-4o"

    def test_reverse_rpc_transport_normalize_usage(self):
        t = ReverseRpcTransport(credential_ref="c", model="m")
        stats = t.normalize_usage({"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30})
        assert isinstance(stats, UsageStats)
        assert stats.prompt_tokens == 10
        assert stats.total_tokens == 30

    def test_create_transport_returns_reverse_rpc(self):
        t = create_transport(credential_ref="cred-1", model="gpt-4o")
        assert isinstance(t, ReverseRpcTransport)
        assert t._credential_ref == "cred-1"

    @pytest.mark.asyncio
    async def test_reverse_rpc_transport_complete_uses_credential_http_start(self):
        t = ReverseRpcTransport(credential_ref="cred-1", model="gpt-4o")
        with pytest.raises(RuntimeError, match="Credential Broker is not configured"):
            await t.complete(
                messages=({"role": "user", "content": "hello"},),
                tool_names=("bash",),
            )
        assert t._rpc.last_method == "credential.http.start"

    @pytest.mark.asyncio
    async def test_reverse_rpc_transport_probe_uses_credential_probe(self):
        t = ReverseRpcTransport(credential_ref="cred-1", model="gpt-4o")
        with pytest.raises(RuntimeError, match="Credential Broker is not configured"):
            await t.probe()
        assert t._rpc.last_method == "credential.probe"

    @pytest.mark.asyncio
    async def test_reverse_rpc_client_stores_last_call(self):
        client = ReverseRpcClient()
        with pytest.raises(RuntimeError, match="Credential Broker is not configured"):
            await client.call("test.method", {"key": "val"})
        assert client.last_method == "test.method"
        assert client.last_params == {"key": "val"}


# ── transport extended (new features) ───────────────────────────────
class TestMarkSidecarOwnSocket:
    def test_mark_and_clear(self):
        mark_sidecar_own_socket("/tmp/sidecar.sock")
        assert get_reverse_rpc_socket_path() is None  # separate global
        mark_sidecar_own_socket(None)
        assert get_reverse_rpc_socket_path() is None

    def test_mark_none_clears(self):
        mark_sidecar_own_socket("/tmp/s.sock")
        mark_sidecar_own_socket(None)


class TestReverseRpcClientSelfConnectionGuard:
    @pytest.mark.asyncio
    async def test_raises_when_socket_matches_own(self):
        import ibreeze.runtime.transport as transport_mod

        with patch.object(transport_mod, "_sidecar_own_socket", "/tmp/own.sock"):
            client = ReverseRpcClient(socket_path="/tmp/own.sock")
            with pytest.raises(RuntimeError, match="cannot connect to Sidecar's own"):
                await client.call("test.method", {})

    @pytest.mark.asyncio
    async def test_raises_when_default_socket_matches_own(self):
        import ibreeze.runtime.transport as transport_mod

        mark_sidecar_own_socket("/tmp/default.sock")
        try:
            with patch.object(transport_mod, "_default_socket_path", "/tmp/default.sock"):
                client = ReverseRpcClient()
                with pytest.raises(RuntimeError, match="cannot connect to Sidecar's own"):
                    await client.call("test.method", {})
        finally:
            mark_sidecar_own_socket(None)

    @pytest.mark.asyncio
    async def test_stores_last_method_on_self_connection_error(self):
        import ibreeze.runtime.transport as transport_mod

        with patch.object(transport_mod, "_sidecar_own_socket", "/tmp/own.sock"):
            client = ReverseRpcClient(socket_path="/tmp/own.sock")
            with pytest.raises(RuntimeError, match="cannot connect to Sidecar's own"):
                await client.call("self.check", {"x": 1})
            assert client.last_method == "self.check"
            assert client.last_params == {"x": 1}

    @pytest.mark.asyncio
    async def test_does_not_block_stub_mode(self):
        import ibreeze.runtime.transport as transport_mod

        with patch.object(transport_mod, "_sidecar_own_socket", "/tmp/own.sock"):
            client = ReverseRpcClient()  # no socket_path -> stub mode
            with pytest.raises(RuntimeError, match="Credential Broker is not configured"):
                await client.call("test.method", {})


class TestReverseRpcTransportProfileDirectoryId:
    @pytest.mark.asyncio
    async def test_probe_passes_profile_directory_id(self):
        t = ReverseRpcTransport(
            credential_ref="cred-1",
            model="gpt-4o",
            profile_directory_id="dir-abc-123",
        )
        with pytest.raises(RuntimeError, match="Credential Broker is not configured"):
            await t.probe()
        params = t._rpc.last_params
        assert params.get("profile_directory_id") == "dir-abc-123"
        assert params.get("credential_ref") == "cred-1"

    @pytest.mark.asyncio
    async def test_probe_defaults_profile_directory_id_to_empty(self):
        t = ReverseRpcTransport(credential_ref="cred-1", model="gpt-4o")
        with pytest.raises(RuntimeError, match="Credential Broker is not configured"):
            await t.probe()
        params = t._rpc.last_params
        assert params.get("profile_directory_id") == ""

    @pytest.mark.asyncio
    async def test_complete_passes_profile_directory_id(self):
        t = ReverseRpcTransport(
            credential_ref="cred-1",
            model="gpt-4o",
            profile_directory_id="dir-xyz",
        )
        with pytest.raises(RuntimeError, match="Credential Broker is not configured"):
            await t.complete(
                messages=({"role": "user", "content": "hi"},),
                tool_names=("bash",),
            )
        params = t._rpc.last_params
        assert params.get("profile_directory_id") == "dir-xyz"
        assert params.get("credential_ref") == "cred-1"
        assert params.get("protocol") == "https"

    @pytest.mark.asyncio
    async def test_complete_defaults_profile_directory_id_to_empty(self):
        t = ReverseRpcTransport(credential_ref="cred-1", model="gpt-4o")
        with pytest.raises(RuntimeError, match="Credential Broker is not configured"):
            await t.complete(
                messages=({"role": "user", "content": "hi"},),
                tool_names=("bash",),
            )
        params = t._rpc.last_params
        assert params.get("profile_directory_id") == ""

    def test_create_transport_passes_profile_directory_id(self):
        t = create_transport(
            credential_ref="c",
            model="m",
            profile_directory_id="dir-789",
        )
        assert t._profile_directory_id == "dir-789"

    def test_reverse_rpc_transport_init_stores_profile_directory_id(self):
        t = ReverseRpcTransport(
            credential_ref="c",
            model="m",
            profile_directory_id="dir-000",
        )
        assert t._profile_directory_id == "dir-000"


# ── event_normalizer ─────────────────────────────────────────────────
class TestEventNormalizer:
    def test_normalize_event(self):
        ev = normalize_event({"type": "run.started", "data": {"k": "v"}}, "run-1", 1, trace_id="t1")
        assert ev["run_id"] == "run-1"
        assert ev["sequence"] == 1
        assert ev["event_type"] == "run.started"
        assert json.loads(ev["payload_json"]) == {"k": "v"}

    def test_create_run_started(self):
        ev = create_run_started("r1", 1, employee_id="e1", model_id="m1")
        assert ev["event_type"] == "run.started"

    def test_create_run_completed(self):
        ev = create_run_completed("r1", 2, summary="done")
        assert ev["event_type"] == "run.completed"

    def test_create_run_failed(self):
        ev = create_run_failed("r1", 3, error="boom")
        assert ev["event_type"] == "run.failed"

    def test_create_run_cancelled(self):
        ev = create_run_cancelled("r1", 4, reason="timeout")
        assert ev["event_type"] == "run.cancelled"

    def test_create_model_delta(self):
        ev = create_model_delta("r1", 5, delta="hello")
        assert ev["event_type"] == "model.output.delta"

    def test_create_model_done(self):
        ev = create_model_done("r1", 6, output="final")
        assert ev["event_type"] == "model.output.done"

    def test_create_tool_event_valid(self):
        for status in ("requested", "started", "completed", "failed"):
            ev = create_tool_event("r1", 7, tool_name="bash", status=status)
            assert ev["event_type"] == f"tool.{status}"

    def test_create_tool_event_invalid(self):
        with pytest.raises(ValueError, match="Invalid tool status"):
            create_tool_event("r1", 7, tool_name="bash", status="invalid")

    def test_create_checkpoint_created(self):
        ev = create_checkpoint("r1", 8, checkpoint_id="cp-1")
        assert ev["event_type"] == "checkpoint.created"

    def test_create_checkpoint_restored(self):
        ev = create_checkpoint("r1", 9, checkpoint_id="cp-1", restored=True)
        assert ev["event_type"] == "checkpoint.restored"

    def test_create_approval_event(self):
        ev = create_approval_event("r1", 10, tool_name="bash", status="requested")
        assert ev["event_type"] == "approval.requested"

    def test_create_approval_event_invalid(self):
        with pytest.raises(ValueError, match="Invalid approval status"):
            create_approval_event("r1", 10, tool_name="bash", status="invalid")

    def test_create_compacted_event(self):
        ev = create_compacted_event("r1", 1, original_events=[{"x": 1}], compacted_data={"summary": "ok"})
        assert ev["event_type"] == "model.output.compacted"
        assert json.loads(ev["payload_json"])["original_count"] == 1

    def test_create_tool_approved_event(self):
        ev = create_tool_approved_event("r1", 1, tool_name="bash", tool_args={"cmd": "ls"})
        assert ev["event_type"] == "tool.approved"

    def test_create_tool_rejected_event(self):
        ev = create_tool_rejected_event("r1", 1, tool_name="rm", reason="unsafe")
        assert ev["event_type"] == "tool.rejected"

    def test_create_workspace_changed_event(self):
        ev = create_workspace_changed_event("r1", 1, changes=[{"file": "a.py"}])
        assert ev["event_type"] == "workspace.changed"

    def test_create_verification_started_event(self):
        ev = create_verification_started_event("r1", 1, target_run_id="target-1")
        assert ev["event_type"] == "verification.started"

    def test_create_verification_completed_event(self):
        ev = create_verification_completed_event("r1", 1, verdict="passed", issues=[])
        assert ev["event_type"] == "verification.completed"

    def test_all_event_types_present(self):
        assert len(EVENT_TYPES) == 14

    @pytest.mark.asyncio
    async def test_store_event(self, db):
        company_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        await _setup_gateway_env(db, company_id)
        await _create_task(db, company_id, task_id)
        emp_row = await (await db.execute("SELECT id FROM employees WHERE company_id=?", (company_id,))).fetchone()
        conv_row = await (await db.execute(
            "SELECT id FROM conversations WHERE company_id=? AND conversation_type='company'",
            (company_id,),
        )).fetchone()
        await _create_run(db, company_id, run_id, task_id, emp_row["id"], conv_row["id"])
        ev = create_run_started(run_id, 1, employee_id=emp_row["id"], model_id="gpt-4o")
        eid = await store_event(db, ev)
        assert eid == ev["event_id"]
        cursor = await db.execute("SELECT event_type FROM agent_run_events WHERE run_id=?", (run_id,))
        row = await cursor.fetchone()
        assert row["event_type"] == "run.started"


# ── UdsConnection ────────────────────────────────────────────────────
@pytest.mark.asyncio
class TestUdsConnection:
    async def test_connect_and_close(self):
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_task = AsyncMock()

        with patch("asyncio.open_unix_connection", return_value=(mock_reader, mock_writer)):
            with patch("asyncio.create_task", return_value=mock_task):
                conn = UdsConnection("/tmp/test.sock")
                await conn.connect()

        assert conn._reader is mock_reader
        assert conn._writer is mock_writer

        await conn.close()
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_awaited_once()
        assert conn._writer is None

    async def test_call_success(self):
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_writer.drain = AsyncMock()
        conn = UdsConnection("/tmp/test.sock")
        conn._writer = mock_writer

        fixed_uuid = uuid.UUID("00000000-0000-0000-0000-000000000001")
        with patch("ibreeze.runtime.transport.uuid4", return_value=fixed_uuid):
            req_id = f"sidecar:{fixed_uuid}"
            call_task = asyncio.create_task(conn.call("test.method", {"key": "val"}))
            await asyncio.sleep(0)
            conn._pending[req_id].set_result({"result": {"status": "ok"}})
            result = await call_task

        assert result == {"status": "ok"}
        mock_writer.write.assert_called_once()
        mock_writer.drain.assert_awaited_once()

    async def test_call_error_response(self):
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_writer.drain = AsyncMock()
        conn = UdsConnection("/tmp/test.sock")
        conn._writer = mock_writer

        fixed_uuid = uuid.UUID("00000000-0000-0000-0000-000000000002")
        with patch("ibreeze.runtime.transport.uuid4", return_value=fixed_uuid):
            req_id = f"sidecar:{fixed_uuid}"
            call_task = asyncio.create_task(conn.call("test.method", {}))
            await asyncio.sleep(0)
            conn._pending[req_id].set_result({"error": {"code": -32601, "message": "Method not found"}})
            with pytest.raises(RuntimeError, match="RPC error"):
                await call_task

    async def test_call_not_connected(self):
        conn = UdsConnection("/tmp/test.sock")
        with pytest.raises(RuntimeError, match="UDS connection not established"):
            await conn.call("test.method", {})

    async def test_call_error_non_dict_response(self):
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_writer.drain = AsyncMock()
        conn = UdsConnection("/tmp/test.sock")
        conn._writer = mock_writer

        fixed_uuid = uuid.UUID("00000000-0000-0000-0000-000000000003")
        with patch("ibreeze.runtime.transport.uuid4", return_value=fixed_uuid):
            req_id = f"sidecar:{fixed_uuid}"
            call_task = asyncio.create_task(conn.call("test.method", {}))
            await asyncio.sleep(0)
            conn._pending[req_id].set_result({"error": "something went wrong"})
            with pytest.raises(RuntimeError, match="RPC error: something went wrong"):
                await call_task

    async def test_call_result_not_dict(self):
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_writer.drain = AsyncMock()
        conn = UdsConnection("/tmp/test.sock")
        conn._writer = mock_writer

        fixed_uuid = uuid.UUID("00000000-0000-0000-0000-000000000004")
        with patch("ibreeze.runtime.transport.uuid4", return_value=fixed_uuid):
            req_id = f"sidecar:{fixed_uuid}"
            call_task = asyncio.create_task(conn.call("test.method", {}))
            await asyncio.sleep(0)
            conn._pending[req_id].set_result({"result": "just a string"})
            result = await call_task

        assert result == {}

    async def test_close_exception(self):
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_writer.wait_closed = AsyncMock(side_effect=RuntimeError("connection reset"))
        mock_task = AsyncMock()

        with patch("asyncio.open_unix_connection", return_value=(mock_reader, mock_writer)):
            with patch("asyncio.create_task", return_value=mock_task):
                conn = UdsConnection("/tmp/test.sock")
                await conn.connect()

        await conn.close()
        mock_writer.close.assert_called_once()
        assert conn._writer is None

    async def test_read_loop_resolves_pending(self):
        conn = UdsConnection("/tmp/test.sock")
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        conn._reader = mock_reader

        req_id = "sidecar:read-loop-test"
        frame = {"jsonrpc": "2.0", "id": req_id, "result": {"done": True}}
        payload = json.dumps(frame, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        length_prefix = len(payload).to_bytes(4, "big")

        mock_reader.readexactly = AsyncMock(side_effect=[
            length_prefix,
            payload,
            asyncio.IncompleteReadError(b"", 4),
        ])

        fut = asyncio.get_event_loop().create_future()
        conn._pending[req_id] = fut

        assert not fut.done()
        await conn._read_loop()

        assert fut.done()
        assert fut.result() == frame
        assert conn._pending == {}

    async def test_read_loop_connection_lost(self):
        conn = UdsConnection("/tmp/test.sock")
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        conn._reader = mock_reader
        mock_reader.readexactly = AsyncMock(side_effect=ConnectionError("pipe broken"))

        fut = asyncio.get_event_loop().create_future()
        conn._pending["req-1"] = fut

        await conn._read_loop()

        assert fut.done()
        assert isinstance(fut.exception(), RuntimeError)
        assert "IPC_CONNECTION_LOST" in str(fut.exception())
        assert conn._pending == {}


# ── encode/decode frame ──────────────────────────────────────────────
class TestEncodeDecodeFrame:
    def test_encode_frame_success(self):
        obj: dict[str, object] = {"jsonrpc": "2.0", "method": "test", "params": {}}
        result = _encode_frame(obj)
        payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        expected = len(payload).to_bytes(4, "big") + payload
        assert result == expected

    def test_encode_frame_oversize(self):
        large_obj: dict[str, object] = {"data": "x" * (MAX_FRAME_BYTES + 1)}
        with pytest.raises(RuntimeError, match="Frame exceeds max size"):
            _encode_frame(large_obj)

    @pytest.mark.asyncio
    async def test_read_frame_success(self):
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        frame: dict[str, object] = {"jsonrpc": "2.0", "method": "ping", "params": {}}
        payload = json.dumps(frame, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        length = len(payload)
        mock_reader.readexactly = AsyncMock(side_effect=[length.to_bytes(4, "big"), payload])
        result = await _read_frame(mock_reader)
        assert result == frame

    @pytest.mark.asyncio
    async def test_read_frame_invalid_length_zero(self):
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_reader.readexactly = AsyncMock(return_value=(0).to_bytes(4, "big"))
        with pytest.raises(RuntimeError, match="Invalid frame length"):
            await _read_frame(mock_reader)

    @pytest.mark.asyncio
    async def test_read_frame_invalid_length_oversize(self):
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_reader.readexactly = AsyncMock(return_value=(MAX_FRAME_BYTES + 1).to_bytes(4, "big"))
        with pytest.raises(RuntimeError, match="Invalid frame length"):
            await _read_frame(mock_reader)


# ── global state helpers ──────────────────────────────────────────────
class TestSetReverseRpcSocketPath:
    def test_set_and_get(self):
        set_reverse_rpc_socket_path("/tmp/rpc.sock")
        assert get_reverse_rpc_socket_path() == "/tmp/rpc.sock"
        set_reverse_rpc_socket_path(None)
        assert get_reverse_rpc_socket_path() is None

    def test_set_none_clears(self):
        set_reverse_rpc_socket_path("/tmp/other.sock")
        set_reverse_rpc_socket_path(None)
        assert get_reverse_rpc_socket_path() is None


class TestReverseRpcClientEnsureConnected:
    @pytest.mark.asyncio
    async def test_ensure_connected_and_call(self):
        import ibreeze.runtime.transport as transport_mod

        mock_conn = AsyncMock(spec=UdsConnection)
        mock_conn.call = AsyncMock(return_value={"status": "ok"})

        with patch.object(transport_mod, "_default_socket_path", "/tmp/real.sock"):
            with patch.object(transport_mod, "_sidecar_own_socket", None):
                with patch.object(transport_mod, "UdsConnection", return_value=mock_conn):
                    client = ReverseRpcClient()
                    result = await client.call("test.method", {"key": "val"})
                    assert result == {"status": "ok"}
                    mock_conn.connect.assert_awaited_once()
                    mock_conn.call.assert_awaited_once_with("test.method", {"key": "val"})

    @pytest.mark.asyncio
    async def test_ensure_connected_reuses_connection(self):
        import ibreeze.runtime.transport as transport_mod

        mock_conn = AsyncMock(spec=UdsConnection)
        mock_conn.call = AsyncMock(return_value={"result": {"ok": True}})

        with patch.object(transport_mod, "_default_socket_path", "/tmp/real.sock"):
            with patch.object(transport_mod, "_sidecar_own_socket", None):
                with patch.object(transport_mod, "UdsConnection", return_value=mock_conn):
                    client = ReverseRpcClient()
                    await client.call("m1", {})
                    await client.call("m2", {})
                    assert mock_conn.connect.await_count == 1
                    assert mock_conn.call.await_count == 2


class TestReverseRpcTransportWithConnection:
    @pytest.mark.asyncio
    async def test_complete_with_connection(self):
        import ibreeze.runtime.transport as transport_mod

        mock_conn = AsyncMock(spec=UdsConnection)
        mock_conn.call = AsyncMock(return_value={
            "content": "Hello", "tool_calls": [], "usage": {"total_tokens": 5},
        })

        with patch.object(transport_mod, "_default_socket_path", "/tmp/real.sock"):
            with patch.object(transport_mod, "_sidecar_own_socket", None):
                with patch.object(transport_mod, "UdsConnection", return_value=mock_conn):
                    t = ReverseRpcTransport(credential_ref="cred-1", model="gpt-4o")
                    result = await t.complete(
                        messages=({"role": "user", "content": "hi"},),
                        tool_names=("bash",),
                    )
                    assert isinstance(result, ModelTurn)
                    assert result.content == "Hello"

    @pytest.mark.asyncio
    async def test_probe_with_connection(self):
        import ibreeze.runtime.transport as transport_mod

        mock_conn = AsyncMock(spec=UdsConnection)
        mock_conn.call = AsyncMock(return_value={"status": "ok"})

        with patch.object(transport_mod, "_default_socket_path", "/tmp/real.sock"):
            with patch.object(transport_mod, "_sidecar_own_socket", None):
                with patch.object(transport_mod, "UdsConnection", return_value=mock_conn):
                    t = ReverseRpcTransport(credential_ref="cred-1", model="gpt-4o")
                    assert await t.probe() is True

    @pytest.mark.asyncio
    async def test_probe_with_connection_not_ok(self):
        import ibreeze.runtime.transport as transport_mod

        mock_conn = AsyncMock(spec=UdsConnection)
        mock_conn.call = AsyncMock(return_value={"status": "error"})

        with patch.object(transport_mod, "_default_socket_path", "/tmp/real.sock"):
            with patch.object(transport_mod, "_sidecar_own_socket", None):
                with patch.object(transport_mod, "UdsConnection", return_value=mock_conn):
                    t = ReverseRpcTransport(credential_ref="cred-1", model="gpt-4o")
                    assert await t.probe() is False


class TestUdsConnectionRemaining:
    @pytest.mark.asyncio
    async def test_read_loop_reader_none(self):
        conn = UdsConnection("/tmp/test.sock")
        await conn._read_loop()

    @pytest.mark.asyncio
    async def test_read_loop_generic_exception(self):
        conn = UdsConnection("/tmp/test.sock")
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        conn._reader = mock_reader

        payload = b"not valid json"
        mock_reader.readexactly = AsyncMock(side_effect=[
            len(payload).to_bytes(4, "big"),
            payload,
        ])
        await conn._read_loop()

    @pytest.mark.asyncio
    async def test_close_no_writer(self):
        conn = UdsConnection("/tmp/test.sock")
        await conn.close()


class TestReadFrameNotADict:
    @pytest.mark.asyncio
    async def test_read_frame_not_a_dict(self):
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        payload = json.dumps(["not", "a", "dict"]).encode("utf-8")
        mock_reader.readexactly = AsyncMock(side_effect=[
            len(payload).to_bytes(4, "big"),
            payload,
        ])
        with pytest.raises(RuntimeError, match="Top-level frame must be a JSON object"):
            await _read_frame(mock_reader)
