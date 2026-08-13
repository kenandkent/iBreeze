"""Coverage tests for workspace.git_ops and workspace.service apply_workspace branches.

Targets the uncovered lines:
- git_ops.py: create_worktree branch-naming (57), INVALID_WORKTREE_NAME (60),
  INVALID_WORKTREE_PATH (64), BRANCH_CREATE_FAILED (68), remove_worktree
  INVALID_WORKTREE_NAME (87), get_merge_conflicts with output (122)
- workspace/service.py: apply_workspace error branches 234, 236, 249, 264,
  285-286, 301, 322
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from ibreeze.workspace.git_ops import (
    create_worktree,
    get_merge_conflicts,
    remove_worktree,
)
from ibreeze.workspace.service import apply_workspace

NOW = "2026-01-15T10:30:00.000000Z"


def _git_ok(**overrides) -> dict[str, object]:
    result = {
        "success": True,
        "stdout": "",
        "stderr": "",
        "exit_code": 0,
    }
    result.update(overrides)
    return result


def _row(**overrides) -> dict[str, object]:
    row = {
        "id": "ws-1",
        "company_id": "co-1",
        "company_task_id": "ct-1",
        "workspace_grant_id": "wg-1",
        "repository_root": "/repo",
        "baseline_commit_sha": "a" * 40,
        "user_branch_name": "feature/test",
        "integration_branch_name": "main",
        "integration_worktree_path": "/wt",
        "status": "ready_to_apply",
        "applied_commit_sha": None,
        "cleaned_at": None,
        "created_at": NOW,
        "updated_at": NOW,
        "version": 1,
    }
    row.update(overrides)
    return row


def _mock_db(row: dict[str, object], update_rowcount: int = 1) -> AsyncMock:
    """db.execute returns the row for SELECTs and a rowcount cursor for UPDATEs."""
    db = AsyncMock()

    def execute_side_effect(sql: str, *args, **kwargs):
        cursor = AsyncMock()
        if sql.strip().startswith("SELECT"):
            cursor.fetchone = AsyncMock(return_value=row)
        else:
            cursor.rowcount = update_rowcount
        return cursor

    db.execute = AsyncMock(side_effect=execute_side_effect)
    return db


# ── git_ops.create_worktree ────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCreateWorktreeCoverage:
    async def test_branch_naming_from_task_and_employee(self, tmp_path):
        """git_ops.py:57 — task+employee compose the ibreeze branch name."""
        git = AsyncMock(side_effect=[_git_ok(), _git_ok()])
        with patch("ibreeze.workspace.git_ops.git_command", git):
            result = await create_worktree(
                str(tmp_path),
                "wt1",
                "ignored",
                task_id="t-123",
                employee_id="e-9",
                attempt=2,
            )
        assert result["success"] is True
        assert result["branch"] == "ibreeze/t-123/e-9/2"
        assert git.await_count == 2

    async def test_invalid_worktree_name(self, tmp_path):
        """git_ops.py:60 — slash-containing name is rejected before any git call."""
        git = AsyncMock()
        with patch("ibreeze.workspace.git_ops.git_command", git):
            result = await create_worktree(str(tmp_path), "a/b", "feat")
        assert result["success"] is False
        assert result["error"] == "INVALID_WORKTREE_NAME"
        git.assert_not_awaited()

    async def test_invalid_worktree_path(self, tmp_path):
        """git_ops.py:64 — '.' escapes the worktrees root lexically."""
        git = AsyncMock()
        with patch("ibreeze.workspace.git_ops.git_command", git):
            result = await create_worktree(str(tmp_path), ".", "feat")
        assert result["success"] is False
        assert result["error"] == "INVALID_WORKTREE_PATH"
        git.assert_not_awaited()

    async def test_branch_create_failure(self, tmp_path):
        """git_ops.py:68 — branch creation failure surfaces BRANCH_CREATE_FAILED."""
        git = AsyncMock(side_effect=[_git_ok(success=False, stderr="", exit_code=128)])
        with patch("ibreeze.workspace.git_ops.git_command", git):
            result = await create_worktree(str(tmp_path), "wt1", "feat")
        assert result["success"] is False
        assert result["error"] == "BRANCH_CREATE_FAILED"
        assert result["branch"] == "feat"


# ── git_ops.remove_worktree / get_merge_conflicts ──────────────────────────


@pytest.mark.asyncio
class TestRemoveWorktreeAndConflictsCoverage:
    async def test_remove_worktree_invalid_name(self, tmp_path):
        """git_ops.py:87 — slash-containing name is rejected."""
        git = AsyncMock()
        with patch("ibreeze.workspace.git_ops.git_command", git):
            result = await remove_worktree(str(tmp_path), "a/b")
        assert result["success"] is False
        assert result["error"] == "INVALID_WORKTREE_NAME"
        git.assert_not_awaited()

    async def test_get_merge_conflicts_returns_files(self, tmp_path):
        """git_ops.py:122 — stdout lines are split into the conflict list."""
        git = AsyncMock(side_effect=[_git_ok(stdout="file1.txt\nsrc/main.py\n")])
        with patch("ibreeze.workspace.git_ops.git_command", git):
            conflicts = await get_merge_conflicts(str(tmp_path))
        assert conflicts == ["file1.txt", "src/main.py"]


# ── workspace.service.apply_workspace error branches ───────────────────────


@pytest.mark.asyncio
class TestApplyWorkspaceCoverage:
    async def test_invalid_status_raises(self):
        """service.py:234 — non-ready_to_apply workspace is rejected."""
        db = _mock_db(_row(status="active"))
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await apply_workspace(db, "co-1", "ws-1", expected_version=1)

    async def test_version_mismatch_raises(self):
        """service.py:236 — stale expected_version is rejected."""
        db = _mock_db(_row(version=2))
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await apply_workspace(db, "co-1", "ws-1", expected_version=1)

    async def test_integration_branch_mismatch(self):
        """service.py:249 — HEAD branch not equal to integration branch."""
        db = _mock_db(_row())
        git = AsyncMock(
            side_effect=[
                _git_ok(),  # integration status (clean)
                _git_ok(stdout="different\n"),  # integration symbolic-ref
            ]
        )
        with patch("ibreeze.workspace.git_ops.git_command", git):
            with pytest.raises(ValueError, match="WORKSPACE_ACCESS_DENIED"):
                await apply_workspace(db, "co-1", "ws-1", expected_version=1)

    async def test_user_worktree_dirty(self):
        """service.py:264 — user worktree drift blocks apply."""
        db = _mock_db(_row())
        git = AsyncMock(
            side_effect=[
                _git_ok(),  # integration status
                _git_ok(stdout="main\n"),  # integration symbolic-ref
                _git_ok(stdout=" M modified.txt\n"),  # user status dirty
                _git_ok(stdout="feature/test\n"),  # user symbolic-ref
                _git_ok(stdout="a" * 40 + "\n"),  # user rev-parse
            ]
        )
        with patch("ibreeze.workspace.git_ops.git_command", git):
            with pytest.raises(ValueError, match="WORKSPACE_ACCESS_DENIED"):
                await apply_workspace(db, "co-1", "ws-1", expected_version=1)

    async def test_commit_failure_aborts_merge(self):
        """service.py:285-286 — failed commit aborts merge and raises."""
        db = _mock_db(_row())
        baseline = "a" * 40
        git = AsyncMock(
            side_effect=[
                _git_ok(),  # integration status
                _git_ok(stdout="main\n"),  # integration symbolic-ref
                _git_ok(),  # user status
                _git_ok(stdout="feature/test\n"),  # user symbolic-ref
                _git_ok(stdout=baseline + "\n"),  # user rev-parse
                _git_ok(),  # merge --no-ff --no-commit
                _git_ok(success=False, stderr="commit failed", exit_code=1),  # commit
                _git_ok(),  # merge --abort
            ]
        )
        with patch("ibreeze.workspace.git_ops.git_command", git):
            with pytest.raises(ValueError, match="COMMIT_FAILED"):
                await apply_workspace(db, "co-1", "ws-1", expected_version=1)
        assert git.await_count == 8

    async def test_success_path_optimistic_lock(self):
        """service.py:301 — rowcount 0 on the applied UPDATE raises."""
        db = _mock_db(_row(), update_rowcount=0)
        git = AsyncMock(
            side_effect=[
                _git_ok(),  # integration status
                _git_ok(stdout="main\n"),  # integration symbolic-ref
                _git_ok(),  # user status
                _git_ok(stdout="feature/test\n"),  # user symbolic-ref
                _git_ok(stdout="a" * 40 + "\n"),  # user rev-parse
                _git_ok(),  # merge --no-ff --no-commit
                _git_ok(),  # commit
                _git_ok(stdout="abc123\n"),  # rev-parse HEAD
            ]
        )
        with patch("ibreeze.workspace.git_ops.git_command", git):
            with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
                await apply_workspace(db, "co-1", "ws-1", expected_version=1)

    async def test_conflict_path_optimistic_lock(self):
        """service.py:322 — rowcount 0 on the ready_to_apply UPDATE raises."""
        db = _mock_db(_row(), update_rowcount=0)
        git = AsyncMock(
            side_effect=[
                _git_ok(),  # integration status
                _git_ok(stdout="main\n"),  # integration symbolic-ref
                _git_ok(),  # user status
                _git_ok(stdout="feature/test\n"),  # user symbolic-ref
                _git_ok(stdout="a" * 40 + "\n"),  # user rev-parse
                _git_ok(success=False, stderr="conflict", exit_code=1),  # merge fails
                _git_ok(),  # merge --abort
            ]
        )
        with (
            patch("ibreeze.workspace.git_ops.git_command", git),
            patch(
                "ibreeze.workspace.git_ops.get_merge_conflicts",
                AsyncMock(return_value=["file1.txt"]),
            ),
        ):
            with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
                await apply_workspace(db, "co-1", "ws-1", expected_version=1)
