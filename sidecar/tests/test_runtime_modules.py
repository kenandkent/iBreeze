"""Tests for runtime modules: permission_gateway, token_budget, recovery,
workspace_broker, checkpoint, context_engine, event_compactor, verification_loop."""

from __future__ import annotations

import json
import uuid

import aiosqlite
import pytest

from ibreeze.runtime.checkpoint import (
    create_checkpoint,
    get_latest_checkpoint,
    list_checkpoints,
    restore_checkpoint,
)
from ibreeze.runtime.context_engine import ContextEngine
from ibreeze.runtime.event_compactor import compact_events
from ibreeze.runtime.permission_gateway import (
    PermissionDecision,
    check_permission,
    is_denied,
    requires_approval,
)
from ibreeze.runtime.recovery import recover_stale_runs
from ibreeze.runtime.token_budget import (
    MODEL_LIMITS,
    calculate_budget,
    truncate_to_budget,
)
from ibreeze.runtime.workspace_broker import (
    activate_workspace,
    allocate_workspace,
    get_workspace_path,
)


# ── permission_gateway ──────────────────────────────────────────────
class TestPermissionGateway:
    def test_exact_match_allow(self):
        assert check_permission("read") == PermissionDecision.ALLOW
        assert check_permission("write") == PermissionDecision.ALLOW

    def test_exact_match_ask(self):
        assert check_permission("bash") == PermissionDecision.ASK
        assert check_permission("delete") == PermissionDecision.ASK

    def test_prefix_match(self):
        assert check_permission("read_file") == PermissionDecision.ALLOW
        assert check_permission("bash_exec") == PermissionDecision.ASK
        assert check_permission("write_output") == PermissionDecision.ALLOW

    def test_unknown_tool_defaults_to_ask(self):
        assert check_permission("unknown_tool_xyz") == PermissionDecision.ASK

    def test_custom_rules_override(self):
        rules = {"read": PermissionDecision.DENY, "custom": PermissionDecision.ALLOW}
        assert check_permission("read", custom_rules=rules) == PermissionDecision.DENY
        assert check_permission("custom", custom_rules=rules) == PermissionDecision.ALLOW

    def test_is_denied(self):
        assert is_denied("read", custom_rules={"read": PermissionDecision.DENY})
        assert not is_denied("read")

    def test_requires_approval(self):
        assert requires_approval("bash")
        assert requires_approval("unknown_tool")
        assert not requires_approval("read")


# ── token_budget ─────────────────────────────────────────────────────
class TestTokenBudget:
    def test_calculate_budget_basic(self):
        result = calculate_budget(128000, 4096)
        assert result["context_window"] == 128000
        assert result["output_reserve"] == 4096
        assert result["system_reserve"] > 0
        assert result["user_budget"] > 0
        assert result["user_budget"] + result["system_reserve"] + result["output_reserve"] == 128000

    def test_calculate_budget_large_output_capped(self):
        result = calculate_budget(100000, 100000)
        assert result["output_reserve"] == 20000  # min(100000, floor(100000*0.20))

    def test_calculate_budget_small_output(self):
        result = calculate_budget(100000, 100)
        assert result["output_reserve"] == 100

    def test_truncate_to_budget_short_text(self):
        text = "hello"
        assert truncate_to_budget(text, 100) == "hello"

    def test_truncate_from_end(self):
        text = "a" * 1000
        result = truncate_to_budget(text, 10, from_end=True)
        assert len(result) <= 40
        assert result == text[:40]

    def test_truncate_from_start(self):
        text = "a" * 1000
        result = truncate_to_budget(text, 10, from_end=False)
        assert result == text[-40:]

    def test_model_limits_dict(self):
        assert "gpt-4o" in MODEL_LIMITS
        assert "claude-3" in MODEL_LIMITS


# ── context_engine ───────────────────────────────────────────────────
class TestContextEngine:
    def test_add_message(self):
        engine = ContextEngine(max_tokens=10000)
        engine.add_message("user", "hello")
        usage = engine.get_token_usage()
        assert usage["message_count"] == 1
        assert usage["used_tokens"] > 0

    def test_add_system_prompt(self):
        engine = ContextEngine(max_tokens=10000)
        engine.add_system_prompt("You are helpful")
        engine.add_message("user", "hello")
        ctx = engine.get_context()
        assert ctx[0]["role"] == "system"

    def test_add_tool_result(self):
        engine = ContextEngine(max_tokens=10000)
        engine.add_tool_result("call-1", "result")
        assert engine.get_token_usage()["message_count"] == 1

    def test_truncate_to_budget(self):
        engine = ContextEngine(max_tokens=100)
        for i in range(20):
            engine.add_message("user", f"message {i} " + "x" * 200)
        removed = engine.truncate_to_budget()
        assert removed > 0
        assert engine.get_token_usage()["used_tokens"] <= 100

    def test_pinned_messages_not_truncated(self):
        engine = ContextEngine(max_tokens=100)
        engine.add_system_prompt("Pinned system prompt with some content here for testing purposes")
        engine.add_message("user", "x" * 500)
        engine.truncate_to_budget()
        ctx = engine.get_context()
        assert any(m["role"] == "system" for m in ctx)

    def test_estimate_tokens(self):
        tokens = ContextEngine._estimate_tokens("hello")
        assert tokens > 0
        assert tokens < 100


# ── checkpoint ───────────────────────────────────────────────────────
async def _ensure_agent_run(db: aiosqlite.Connection, run_id: str, company_id: str) -> None:
    now = "2026-01-01T00:00:00Z"
    sha = "a" * 64
    company_task_id = str(uuid.uuid4())
    conv_id = str(uuid.uuid4())
    msg_event = str(uuid.uuid4())
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """INSERT OR IGNORE INTO company_tasks
               (id, company_id, supersedes_task_id, company_conversation_id, user_message_event_id,
                title, status, created_at, updated_at, version)
               VALUES (?, ?, NULL, ?, ?, 'Task', 'draft', ?, ?, 1)""",
            (company_task_id, company_id, conv_id, msg_event, now, now),
        )
        await db.execute(
            """INSERT INTO agent_runs
               (id, company_id, company_task_id, work_item_id, employee_id,
                conversation_id, availability_snapshot_id, execution_snapshot_id,
                run_purpose, adapter_type, run_spec_json, run_spec_sha256,
                status, attempt, created_at, updated_at, version)
               VALUES (?, ?, ?, ?, ?, ?, 'avail', 'exec', 'review', 'codex_cli', '{}', ?,
                       'queued', 1, ?, ?, 1)""",
            (run_id, company_id, company_task_id, company_task_id, str(uuid.uuid4()), str(uuid.uuid4()), sha, now, now),
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()


@pytest.mark.asyncio
class TestCheckpoint:
    async def test_create_and_restore_sqlite_blob(self, db):
        run_id = str(uuid.uuid4())
        company_id = str(uuid.uuid4())
        await _ensure_agent_run(db, run_id, company_id)
        state = {"step": 1, "data": [1, 2, 3]}
        cp = await create_checkpoint(db, run_id=run_id, boundary_type="turn", state_snapshot=state)
        assert cp["sequence"] == 1
        restored = await restore_checkpoint(db, cp["id"])
        assert restored is not None
        assert restored["state_snapshot"] == state

    async def test_create_file_checkpoint(self, db):
        run_id = str(uuid.uuid4())
        company_id = str(uuid.uuid4())
        await _ensure_agent_run(db, run_id, company_id)
        cp = await create_checkpoint(
            db,
            run_id=run_id,
            boundary_type="tool",
            state_snapshot={"k": "v"},
            file_path="/tmp/test_cp.json",
        )
        assert cp["sequence"] == 1

    async def test_get_latest_checkpoint(self, db):
        run_id = str(uuid.uuid4())
        company_id = str(uuid.uuid4())
        await _ensure_agent_run(db, run_id, company_id)
        await create_checkpoint(db, run_id=run_id, boundary_type="a", state_snapshot={"v": 1})
        await create_checkpoint(db, run_id=run_id, boundary_type="b", state_snapshot={"v": 2})
        latest = await get_latest_checkpoint(db, run_id)
        assert latest is not None
        assert latest["sequence"] == 2

    async def test_get_latest_nonexistent(self, db):
        result = await get_latest_checkpoint(db, "nonexistent")
        assert result is None

    async def test_list_checkpoints(self, db):
        run_id = str(uuid.uuid4())
        company_id = str(uuid.uuid4())
        await _ensure_agent_run(db, run_id, company_id)
        await create_checkpoint(db, run_id=run_id, boundary_type="a", state_snapshot={"x": 1})
        await create_checkpoint(db, run_id=run_id, boundary_type="b", state_snapshot={"x": 2})
        cps = await list_checkpoints(db, run_id)
        assert len(cps) == 2
        assert cps[0]["sequence"] >= cps[1]["sequence"]

    async def test_restore_nonexistent(self, db):
        result = await restore_checkpoint(db, "nonexistent-id")
        assert result is None

    async def test_sequence_increments(self, db):
        run_id = str(uuid.uuid4())
        company_id = str(uuid.uuid4())
        await _ensure_agent_run(db, run_id, company_id)
        cp1 = await create_checkpoint(db, run_id=run_id, boundary_type="a", state_snapshot={})
        cp2 = await create_checkpoint(db, run_id=run_id, boundary_type="b", state_snapshot={})
        assert cp2["sequence"] == cp1["sequence"] + 1


# ── event_compactor ──────────────────────────────────────────────────
async def _insert_run_events(db: aiosqlite.Connection, run_id: str, events: list[dict]) -> None:
    for i, ev in enumerate(events, 1):
        await db.execute(
            """INSERT INTO agent_run_events
               (run_id, event_id, sequence, event_type, payload_json, trace_id, occurred_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (run_id, str(uuid.uuid4()), i, ev["type"], json.dumps(ev.get("data", {})), str(uuid.uuid4()), "2026-01-01T00:00:00Z"),
        )
    await db.commit()


@pytest.mark.asyncio
class TestEventCompactor:
    async def test_compact_empty_events(self, db):
        result = await compact_events(db, str(uuid.uuid4()))
        assert result["transcript"] == ""
        assert result["event_count"] == 0

    async def test_compact_with_events(self, db):
        run_id = str(uuid.uuid4())
        company_id = str(uuid.uuid4())
        await _ensure_agent_run(db, run_id, company_id)
        events = [
            {"type": "run.started", "data": {"agent_id": "emp-1", "model_id": "gpt-4o"}},
            {"type": "model.output.done", "data": {"output": "Planning done."}},
            {"type": "tool.completed", "data": {"tool": "bash", "result": "ok"}},
            {"type": "run.completed", "data": {"summary": "All done"}},
        ]
        await _insert_run_events(db, run_id, events)
        result = await compact_events(db, run_id)
        assert result["event_count"] == 4
        assert "Run Started" in result["transcript"]
        assert "Model Output" in result["transcript"]
        assert "Tool: bash" in result["transcript"]

    async def test_compact_writes_marker(self, db):
        run_id = str(uuid.uuid4())
        company_id = str(uuid.uuid4())
        await _ensure_agent_run(db, run_id, company_id)
        events = [
            {"type": "run.started", "data": {}},
            {"type": "run.failed", "data": {"error": "timeout"}},
        ]
        await _insert_run_events(db, run_id, events)
        await compact_events(db, run_id)
        cursor = await db.execute(
            "SELECT event_type FROM agent_run_events WHERE run_id=? ORDER BY sequence DESC LIMIT 1",
            (run_id,),
        )
        marker = await cursor.fetchone()
        assert marker["event_type"] == "compaction.marker"

    async def test_compact_unknown_event_types(self, db):
        run_id = str(uuid.uuid4())
        company_id = str(uuid.uuid4())
        await _ensure_agent_run(db, run_id, company_id)
        await _insert_run_events(db, run_id, [{"type": "custom.unknown", "data": {}}])
        result = await compact_events(db, run_id)
        assert result["event_count"] == 1


# ── recovery ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
class TestRecovery:
    async def test_recover_stale_runs(self, db):
        company_id = str(uuid.uuid4())
        for status in ("queued", "running", "probing", "starting"):
            run_id = str(uuid.uuid4())
            await _ensure_agent_run(db, run_id, company_id)
            await db.execute("UPDATE agent_runs SET status=? WHERE id=?", (status, run_id))
        await db.commit()
        result = await recover_stale_runs(db)
        assert result["recovered"] == 4
        assert result["checked"] == 4

    async def test_recover_no_stale_runs(self, db):
        result = await recover_stale_runs(db)
        assert result["recovered"] == 0

    async def test_recover_does_not_touch_terminal(self, db):
        company_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        await _ensure_agent_run(db, run_id, company_id)
        await db.execute("UPDATE agent_runs SET status='succeeded' WHERE id=?", (run_id,))
        await db.commit()
        result = await recover_stale_runs(db)
        assert result["recovered"] == 0


# ── workspace_broker ─────────────────────────────────────────────────
async def _create_workspace_prereqs(
    db: aiosqlite.Connection,
    company_id: str,
    company_task_id: str,
    workspace_grant_id: str,
):
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
            (company_task_id, company_id, conv_id, msg_event, now, now),
        )
        await db.execute(
            """INSERT INTO workspace_grants
               (id, company_id, normalized_path, security_bookmark, path_type, status, created_at)
               VALUES (?, ?, '/repo', ?, 'code_repository', 'active', ?)""",
            (workspace_grant_id, company_id, b"bookmark", now),
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()


@pytest.mark.asyncio
class TestWorkspaceBroker:
    async def test_allocate_workspace(self, db, tmp_path):
        company_id = str(uuid.uuid4())
        company_task_id = str(uuid.uuid4())
        workspace_grant_id = str(uuid.uuid4())
        await _create_workspace_prereqs(db, company_id, company_task_id, workspace_grant_id)
        ws_path = str(tmp_path / "worktree")
        result = await allocate_workspace(
            db,
            company_id=company_id,
            company_task_id=company_task_id,
            workspace_grant_id=workspace_grant_id,
            repository_root="/repo",
            baseline_commit_sha="a" * 40,
            user_branch_name="feat/test",
            integration_branch_name="integration/test",
            integration_worktree_path=ws_path,
        )
        assert result["status"] == "preparing"
        import os

        assert os.path.isdir(ws_path)

    async def test_activate_workspace(self, db, tmp_path):
        company_id = str(uuid.uuid4())
        company_task_id = str(uuid.uuid4())
        workspace_grant_id = str(uuid.uuid4())
        await _create_workspace_prereqs(db, company_id, company_task_id, workspace_grant_id)
        ws_path = str(tmp_path / "ws2")
        alloc = await allocate_workspace(
            db,
            company_id=company_id,
            company_task_id=company_task_id,
            workspace_grant_id=workspace_grant_id,
            repository_root="/repo",
            baseline_commit_sha="b" * 40,
            user_branch_name="feat/a",
            integration_branch_name="integration/a",
            integration_worktree_path=ws_path,
        )
        result = await activate_workspace(db, alloc["workspace_id"])
        assert result["status"] == "active"

    async def test_get_workspace_path(self, db, tmp_path):
        company_id = str(uuid.uuid4())
        company_task_id = str(uuid.uuid4())
        workspace_grant_id = str(uuid.uuid4())
        await _create_workspace_prereqs(db, company_id, company_task_id, workspace_grant_id)
        ws_path = str(tmp_path / "ws3")
        alloc = await allocate_workspace(
            db,
            company_id=company_id,
            company_task_id=company_task_id,
            workspace_grant_id=workspace_grant_id,
            repository_root="/repo",
            baseline_commit_sha="c" * 40,
            user_branch_name="feat/b",
            integration_branch_name="integration/b",
            integration_worktree_path=ws_path,
        )
        path = await get_workspace_path(db, alloc["workspace_id"])
        assert path == ws_path

    async def test_get_workspace_path_nonexistent(self, db):
        path = await get_workspace_path(db, "nonexistent")
        assert path is None
