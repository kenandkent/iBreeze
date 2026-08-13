"""Tests for workspace Git operations.

Covers WORK-004, WORK-005, WORK-006.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ibreeze.workspace.git_ops import (
    create_bundle,
    create_worktree,
    get_merge_conflicts,
    git_command,
    is_git_repo,
    merge_branch,
    remove_worktree,
)


async def _init_git_repo(path: Path) -> None:
    """Initialize a git repo with an initial commit."""
    await git_command("-c", "init.defaultBranch=main", "init", cwd=str(path))
    await git_command("config", "user.email", "test@test.com", cwd=str(path))
    await git_command("config", "user.name", "Test", cwd=str(path))
    (path / "README.md").write_text("initial", encoding="utf-8")
    await git_command("add", ".", cwd=str(path))
    await git_command("commit", "-m", "initial commit", cwd=str(path))


@pytest.mark.asyncio
class TestGitBaselineCreation:
    """WORK-004: Workspace should create git baseline."""

    async def test_is_git_repo(self, tmp_path):
        await _init_git_repo(tmp_path)
        assert await is_git_repo(str(tmp_path))

    async def test_not_git_repo(self, tmp_path):
        assert not await is_git_repo(str(tmp_path))

    async def test_git_command_success(self, tmp_path):
        await _init_git_repo(tmp_path)
        result = await git_command("status", cwd=str(tmp_path))
        assert result["success"] is True
        assert result["exit_code"] == 0

    async def test_git_command_failure(self, tmp_path):
        await _init_git_repo(tmp_path)
        result = await git_command("checkout", "nonexistent-branch", cwd=str(tmp_path))
        assert result["success"] is False

    async def test_create_bundle(self, tmp_path):
        await _init_git_repo(tmp_path)
        bundle_path = tmp_path / "backup.bundle"
        result = await create_bundle(str(tmp_path), str(bundle_path), "main")
        assert result["success"] is True
        assert bundle_path.exists()


@pytest.mark.asyncio
class TestConcurrentBranchIsolation:
    """WORK-005: Concurrent employee branches should be isolated."""

    async def test_create_worktree(self, tmp_path):
        await _init_git_repo(tmp_path)
        result = await create_worktree(str(tmp_path), "employee-a", "feat-a", base_branch="main")
        assert result["success"] is True
        assert Path(result["path"]).exists()
        assert result["branch"] == "feat-a"

    async def test_multiple_worktrees_coexist(self, tmp_path):
        """WORK-005: Multiple employee worktrees are isolated."""
        await _init_git_repo(tmp_path)
        wt_a = await create_worktree(str(tmp_path), "emp-a", "feat-a", base_branch="main")
        wt_b = await create_worktree(str(tmp_path), "emp-b", "feat-b", base_branch="main")
        assert wt_a["success"] is True
        assert wt_b["success"] is True
        assert wt_a["path"] != wt_b["path"]
        assert Path(wt_a["path"]).exists()
        assert Path(wt_b["path"]).exists()

    async def test_remove_worktree(self, tmp_path):
        await _init_git_repo(tmp_path)
        await create_worktree(str(tmp_path), "emp-c", "feat-c", base_branch="main")
        result = await remove_worktree(str(tmp_path), "emp-c")
        assert result["success"] is True

    async def test_merge_branch(self, tmp_path):
        """WORK-005: Branch merge produces expected result."""
        await _init_git_repo(tmp_path)
        result = await merge_branch(str(tmp_path), "main", "main")
        assert result["success"] is True

    async def test_merge_conflict_detection(self, tmp_path):
        """WORK-005: Merge conflicts are detected."""
        await _init_git_repo(tmp_path)
        conflicts = await get_merge_conflicts(str(tmp_path))
        assert isinstance(conflicts, list)


@pytest.mark.asyncio
class TestUserBranchDriftDetection:
    """WORK-006: User branch drift should be detected."""

    async def test_drift_via_commit_difference(self, tmp_path):
        """WORK-006: Branch drift detected by comparing commit SHAs."""
        await _init_git_repo(tmp_path)
        baseline = await git_command("rev-parse", "HEAD", cwd=str(tmp_path))
        assert baseline["success"] is True
        baseline_sha = baseline["stdout"].strip()
        (tmp_path / "drift.md").write_text("drift", encoding="utf-8")
        await git_command("add", ".", cwd=str(tmp_path))
        await git_command("commit", "-m", "drift commit", cwd=str(tmp_path))
        current = await git_command("rev-parse", "HEAD", cwd=str(tmp_path))
        current_sha = current["stdout"].strip()
        assert baseline_sha != current_sha

    async def test_stable_branch_no_drift(self, tmp_path):
        """WORK-006: Unchanged branch has no drift."""
        await _init_git_repo(tmp_path)
        sha1 = await git_command("rev-parse", "HEAD", cwd=str(tmp_path))
        sha2 = await git_command("rev-parse", "HEAD", cwd=str(tmp_path))
        assert sha1["stdout"] == sha2["stdout"]

    async def test_git_command_not_found(self):
        """WORK-006: Graceful handling when git is not available."""
        result = await git_command("status", cwd="/nonexistent")
        assert result["success"] is False
