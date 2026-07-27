"""Git operations for workspace management."""

from __future__ import annotations

import asyncio
from typing import Any


async def git_command(*args: str, cwd: str | None = None) -> dict[str, Any]:
    """Execute a git command and return result."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return {
            "exit_code": proc.returncode,
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
            "success": proc.returncode == 0,
        }
    except FileNotFoundError:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": "git not found",
            "success": False,
        }


async def create_worktree(
    base_dir: str,
    worktree_name: str,
    branch_name: str,
    base_branch: str = "main",
    *,
    task_id: str = "",
    employee_id: str = "",
    attempt: int = 1,
) -> dict[str, Any]:
    """Create a git worktree for a workspace.

    Branch naming spec: ibreeze/{task_id}/{employee_id}/{attempt}
    """
    import os

    if task_id and employee_id:
        branch_name = f"ibreeze/{task_id}/{employee_id}/{attempt}"

    worktree_path = os.path.join(base_dir, "worktrees", worktree_name)

    await git_command("branch", branch_name, base_branch, cwd=base_dir)
    result = await git_command(
        "worktree", "add", worktree_path, branch_name, cwd=base_dir
    )
    return {
        "path": worktree_path,
        "branch": branch_name,
        "success": result["success"],
        "error": result["stderr"] if not result["success"] else None,
    }


async def remove_worktree(base_dir: str, worktree_name: str) -> dict[str, Any]:
    """Remove a git worktree."""
    import os

    worktree_path = os.path.join(base_dir, "worktrees", worktree_name)
    result = await git_command(
        "worktree", "remove", worktree_path, "--force", cwd=base_dir
    )
    return {
        "success": result["success"],
        "error": result["stderr"] if not result["success"] else None,
    }


async def merge_branch(
    base_dir: str,
    source_branch: str,
    target_branch: str,
) -> dict[str, Any]:
    """Merge source branch into target branch."""
    result = await git_command(
        "merge",
        source_branch,
        "--no-ff",
        "-m",
        f"Merge {source_branch} into {target_branch}",
        cwd=base_dir,
    )
    return {
        "success": result["success"],
        "conflicts": "CONFLICT" in result["stdout"],
        "output": result["stdout"],
        "error": result["stderr"] if not result["success"] else None,
    }


async def get_merge_conflicts(base_dir: str) -> list[str]:
    """List files with merge conflicts."""
    result = await git_command(
        "diff", "--name-only", "--diff-filter=U", cwd=base_dir
    )
    if result["success"] and result["stdout"].strip():
        return result["stdout"].strip().split("\n")  # type: ignore[no-any-return]
    return []


async def create_bundle(
    base_dir: str, output_path: str, branch: str
) -> dict[str, Any]:
    """Create a git bundle for backup."""
    result = await git_command(
        "bundle", "create", output_path, branch, cwd=base_dir
    )
    return {
        "success": result["success"],
        "path": output_path,
        "error": result["stderr"] if not result["success"] else None,
    }


async def is_git_repo(path: str) -> bool:
    """Check if a path is a git repository."""
    result = await git_command("rev-parse", "--git-dir", cwd=path)
    return result["success"]  # type: ignore[no-any-return]
