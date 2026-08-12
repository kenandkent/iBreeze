"""Tests for workspace/service.py — TaskWorkspace state transitions (target: 100%)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from ibreeze.schemas import TaskWorkspaceResponse, TaskWorkspaceStatus
from ibreeze.workspace.service import (
    _datetime,
    _id,
    _now,
    _response,
    abandon_workspace,
    apply_workspace,
    archive_workspace,
    cleanup_workspace,
    create_workspace,
    get_workspace,
    open_workspace,
)

NOW = "2026-01-15T10:30:00.000000Z"


async def _insert_workspace(db, **overrides):
    data = {
        "id": str(uuid.uuid4()),
        "company_id": "co-1",
        "company_task_id": str(uuid.uuid4()),
        "workspace_grant_id": str(uuid.uuid4()),
        "repository_root": "/tmp/repo",
        "baseline_commit_sha": "a" * 40,
        "user_branch_name": "feature/test",
        "integration_branch_name": "main",
        "integration_worktree_path": "/tmp/wt-" + str(uuid.uuid4())[:8],
        "status": "preparing",
        "applied_commit_sha": None,
        "cleaned_at": None,
        "created_at": NOW,
        "updated_at": NOW,
        "version": 1,
    }
    data.update(overrides)
    cols = (
        "id, company_id, company_task_id, workspace_grant_id, repository_root, "
        "baseline_commit_sha, user_branch_name, integration_branch_name, "
        "integration_worktree_path, status, applied_commit_sha, cleaned_at, "
        "created_at, updated_at, version"
    )
    values = (
        data["id"], data["company_id"], data["company_task_id"],
        data["workspace_grant_id"], data["repository_root"],
        data["baseline_commit_sha"], data["user_branch_name"],
        data["integration_branch_name"], data["integration_worktree_path"],
        data["status"], data["applied_commit_sha"], data["cleaned_at"],
        data["created_at"], data["updated_at"], data["version"],
    )
    await db.execute(f"INSERT INTO task_workspaces ({cols}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
    await db.commit()
    return data


# ── Utilities ──────────────────────────────────────────────────────────────


class TestDatetime:
    def test_converts_z_to_utc(self):
        dt = _datetime("2026-01-15T10:30:00.000000Z")
        assert dt == datetime(2026, 1, 15, 10, 30, 0, 0, tzinfo=UTC)

    def test_converts_explicit_offset(self):
        dt = _datetime("2026-01-15T10:30:00.000000+00:00")
        assert dt == datetime(2026, 1, 15, 10, 30, 0, 0, tzinfo=UTC)


class TestResponse:
    def test_creates_model_from_dict(self):
        row = {
            "id": "ws-1", "company_id": "co-1", "company_task_id": "ct-1",
            "workspace_grant_id": "wg-1", "repository_root": "/repo",
            "baseline_commit_sha": "a" * 40, "user_branch_name": "feature/x",
            "integration_branch_name": "main", "integration_worktree_path": "/wt",
            "status": "active", "applied_commit_sha": None, "cleaned_at": None,
            "created_at": "2026-01-15T10:30:00.000000Z",
            "updated_at": "2026-01-15T10:30:00.000000Z",
            "version": 1,
        }
        result = _response(row)
        assert isinstance(result, TaskWorkspaceResponse)
        assert result.id == "ws-1"
        assert result.status == TaskWorkspaceStatus.ACTIVE
        assert result.version == 1
        assert result.cleaned_at is None

    def test_populates_all_fields(self):
        row = {
            "id": "ws-2", "company_id": "co-2", "company_task_id": "ct-2",
            "workspace_grant_id": "wg-2", "repository_root": "/r2",
            "baseline_commit_sha": "b" * 40, "user_branch_name": "feat/y",
            "integration_branch_name": "dev", "integration_worktree_path": "/wt2",
            "status": "applied", "applied_commit_sha": "c" * 40,
            "cleaned_at": "2026-01-16T00:00:00.000000Z",
            "created_at": "2026-01-15T10:30:00.000000Z",
            "updated_at": "2026-01-16T00:00:00.000000Z",
            "version": 3,
        }
        result = _response(row)
        assert result.applied_commit_sha == "c" * 40
        assert result.cleaned_at == "2026-01-16T00:00:00.000000Z"
        assert result.version == 3


class TestId:
    def test_returns_valid_uuid(self):
        val = _id()
        uuid.UUID(val)

    def test_unique(self):
        assert _id() != _id()


class TestNow:
    def test_ends_with_z(self):
        val = _now()
        assert val.endswith("Z")

    def test_roundtrips_through_datetime(self):
        val = _now()
        parsed = _datetime(val)
        assert isinstance(parsed, datetime)


# ── get_workspace ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestGetWorkspace:
    async def test_found(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db)
        result = await get_workspace(db, "co-1", inserted["id"])
        assert result.id == inserted["id"]
        assert result.company_id == "co-1"
        assert result.version == 1

    async def test_not_found(self, db):
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await get_workspace(db, "co-1", "nonexistent")


# ── create_workspace ──────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCreateWorkspace:
    async def test_success(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        result = await create_workspace(
            db,
            company_id="co-1",
            company_task_id=str(uuid.uuid4()),
            workspace_grant_id=str(uuid.uuid4()),
            repository_root="/tmp/repo",
            baseline_commit_sha="b" * 40,
            user_branch_name="feature/test",
            integration_branch_name="main",
            integration_worktree_path="/tmp/wt-" + str(uuid.uuid4())[:8],
        )
        assert result["status"] == "preparing"
        uuid.UUID(result["workspace_id"])
        # Verify it was actually persisted
        ws = await get_workspace(db, "co-1", result["workspace_id"])
        assert ws.status == TaskWorkspaceStatus.PREPARING


# ── open_workspace ────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestOpenWorkspace:
    async def test_success(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db, status="preparing")
        result = await open_workspace(db, "co-1", inserted["id"], expected_version=1)
        assert result.status == TaskWorkspaceStatus.ACTIVE
        assert result.version == 2

    async def test_version_mismatch(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db, status="preparing")
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await open_workspace(db, "co-1", inserted["id"], expected_version=999)

    async def test_invalid_state(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db, status="ready_to_apply")
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await open_workspace(db, "co-1", inserted["id"], expected_version=1)


# ── archive_workspace ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestArchiveWorkspace:
    async def test_success_from_active(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db, status="active")
        result = await archive_workspace(db, "co-1", inserted["id"], expected_version=1)
        assert result.status == TaskWorkspaceStatus.ABANDONED
        assert result.version == 2

    async def test_success_from_preparing(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db, status="preparing")
        result = await archive_workspace(db, "co-1", inserted["id"], expected_version=1)
        assert result.status == TaskWorkspaceStatus.ABANDONED

    async def test_invalid_state_applied(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db, status="applied")
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await archive_workspace(db, "co-1", inserted["id"], expected_version=1)


# ── abandon_workspace ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestAbandonWorkspace:
    async def test_success(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db, status="active")
        result = await abandon_workspace(db, "co-1", inserted["id"], expected_version=1)
        assert result.status == TaskWorkspaceStatus.ABANDONED
        assert result.version == 2

    async def test_optimistic_lock_conflict(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db, status="active", version=2)
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await abandon_workspace(db, "co-1", inserted["id"], expected_version=1)

    async def test_active_runs_block_abandon(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db, status="active")
        # Insert an active agent_run referencing the same company_task_id + company_id
        employee_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO agent_runs
               (id, company_id, company_task_id, department_task_id, employee_task_id,
                work_item_id, employee_id, conversation_id,
                availability_snapshot_id, execution_snapshot_id,
                run_purpose, adapter_type, run_spec_json, run_spec_sha256,
                status, attempt, resume_state, created_at, updated_at, version)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
            (
                run_id, "co-1", inserted["company_task_id"],
                str(uuid.uuid4()), employee_id,
                employee_id, employee_id,
                str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()),
                "task_execution", "codex_cli", "{}",
                "0" * 64,
                "running", 1, None, NOW, NOW,
            ),
        )
        await db.commit()
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await abandon_workspace(db, "co-1", inserted["id"], expected_version=1)


# ── cleanup_workspace ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCleanupWorkspace:
    async def test_success_from_applied(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db, status="applied")
        result = await cleanup_workspace(db, "co-1", inserted["id"], expected_version=1)
        assert result["cleaned"] is True
        assert result["version"] == 2

    async def test_success_from_abandoned(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db, status="abandoned")
        result = await cleanup_workspace(db, "co-1", inserted["id"], expected_version=1)
        assert result["cleaned"] is True

    async def test_already_cleaned(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db, status="applied", cleaned_at=NOW)
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await cleanup_workspace(db, "co-1", inserted["id"], expected_version=1)

    async def test_invalid_state(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db, status="preparing")
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await cleanup_workspace(db, "co-1", inserted["id"], expected_version=1)

    async def test_version_mismatch(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db, status="applied", version=5)
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await cleanup_workspace(db, "co-1", inserted["id"], expected_version=1)


# ── apply_workspace ───────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestApplyWorkspace:
    async def test_success_path(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db, status="ready_to_apply")
        ws_id = inserted["id"]

        mock_git = AsyncMock()
        mock_git.side_effect = [
            {"success": True, "stdout": "", "stderr": "", "exit_code": 0},      # integration status
            {"success": True, "stdout": "main\n", "stderr": "", "exit_code": 0},  # integration branch
            {"success": True, "stdout": "", "stderr": "", "exit_code": 0},      # user status
            {"success": True, "stdout": "feature/test\n", "stderr": "", "exit_code": 0},  # user branch
            {"success": True, "stdout": "a" * 40 + "\n", "stderr": "", "exit_code": 0},  # user baseline
            {"success": True, "stdout": "", "stderr": "", "exit_code": 0},      # merge --no-ff --no-commit
            {"success": True, "stdout": "", "stderr": "", "exit_code": 0},      # commit
            {"success": True, "stdout": "abc123\n", "stderr": "", "exit_code": 0},  # rev-parse HEAD
        ]

        with patch("ibreeze.workspace.git_ops.git_command", mock_git):
            result = await apply_workspace(db, "co-1", ws_id, expected_version=1)

        assert result["status"] == "applied"
        assert result["applied_commit_sha"] == "abc123"

    async def test_conflict_path(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db, status="ready_to_apply")
        ws_id = inserted["id"]

        mock_git = AsyncMock()
        mock_git.side_effect = [
            {"success": True, "stdout": "", "stderr": "", "exit_code": 0},      # integration status
            {"success": True, "stdout": "main\n", "stderr": "", "exit_code": 0},  # integration branch
            {"success": True, "stdout": "", "stderr": "", "exit_code": 0},      # user status
            {"success": True, "stdout": "feature/test\n", "stderr": "", "exit_code": 0},  # user branch
            {"success": True, "stdout": "a" * 40 + "\n", "stderr": "", "exit_code": 0},  # user baseline
            {"success": False, "stdout": "", "stderr": "conflict", "exit_code": 1},  # merge fails
            {"success": True, "stdout": "", "stderr": "", "exit_code": 0},      # merge --abort
        ]

        with (
            patch("ibreeze.workspace.git_ops.git_command", mock_git),
            patch(
                "ibreeze.workspace.git_ops.get_merge_conflicts",
                AsyncMock(return_value=["file1.txt", "src/main.py"]),
            ),
        ):
            result = await apply_workspace(db, "co-1", ws_id, expected_version=1)

        assert result["status"] == "ready_to_apply"
        assert result["conflicts"] == ["file1.txt", "src/main.py"]

    async def test_dirty_workspace(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db, status="ready_to_apply")
        ws_id = inserted["id"]

        mock_git = AsyncMock()
        mock_git.side_effect = [
            {"success": True, "stdout": " M modified.txt\n", "stderr": "", "exit_code": 0},  # dirty
        ]

        with patch("ibreeze.workspace.git_ops.git_command", mock_git):
            with pytest.raises(ValueError, match="WORKSPACE_DIRTY"):
                await apply_workspace(db, "co-1", ws_id, expected_version=1)

    async def test_missing_workspace_path(self, db):
        await db.execute("PRAGMA foreign_keys = OFF")
        inserted = await _insert_workspace(db, status="ready_to_apply")
        ws_id = inserted["id"]

        mock_git = AsyncMock()
        mock_git.side_effect = [
            {"success": False, "stdout": "", "stderr": "not a git repo", "exit_code": 128},
        ]

        with patch("ibreeze.workspace.git_ops.git_command", mock_git):
            with pytest.raises(ValueError, match="WORKSPACE_NOT_FOUND"):
                await apply_workspace(db, "co-1", ws_id, expected_version=1)
