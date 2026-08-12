"""TaskWorkspace state transitions backed by SQLite."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from ibreeze.schemas import TaskWorkspaceResponse


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _one(cursor: Any) -> Any | None:
    return await cursor.fetchone()


def _response(row: Any) -> TaskWorkspaceResponse:
    return TaskWorkspaceResponse(
        id=row["id"],
        company_id=row["company_id"],
        company_task_id=row["company_task_id"],
        workspace_grant_id=row["workspace_grant_id"],
        repository_root=row["repository_root"],
        baseline_commit_sha=row["baseline_commit_sha"],
        user_branch_name=row["user_branch_name"],
        integration_branch_name=row["integration_branch_name"],
        integration_worktree_path=row["integration_worktree_path"],
        status=row["status"],
        applied_commit_sha=row["applied_commit_sha"],
        cleaned_at=row["cleaned_at"],
        created_at=_datetime(row["created_at"]),
        updated_at=_datetime(row["updated_at"]),
        version=row["version"],
    )


async def get_workspace(
    db: Any,
    company_id: str,
    workspace_id: str,
) -> TaskWorkspaceResponse:
    row = await _one(
        await db.execute(
            "SELECT * FROM task_workspaces WHERE id=? AND company_id=?",
            (workspace_id, company_id),
        )
    )
    if row is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    return _response(row)


async def abandon_workspace(
    db: Any,
    company_id: str,
    workspace_id: str,
    *,
    expected_version: int,
) -> TaskWorkspaceResponse:
    """Move a non-applied workspace to its terminal abandoned state."""
    active = await _one(
        await db.execute(
            """SELECT 1 FROM agent_runs r
               JOIN task_workspaces w
                 ON w.company_task_id=r.company_task_id
                AND w.company_id=r.company_id
               WHERE w.id=? AND w.company_id=? AND r.status NOT IN
               ('succeeded','cancelled','timed_out','failed','lost')
               LIMIT 1""",
            (workspace_id, company_id),
        )
    )
    if active is not None:
        raise ValueError("STATE_TRANSITION_INVALID")
    cursor = await db.execute(
        """UPDATE task_workspaces SET status='abandoned',
           updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),version=version+1
           WHERE id=? AND company_id=? AND version=?
             AND status IN ('preparing','active','ready_to_apply')""",
        (workspace_id, company_id, expected_version),
    )
    if cursor.rowcount != 1:
        raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
    return await get_workspace(db, company_id, workspace_id)


async def cleanup_workspace(
    db: Any,
    company_id: str,
    workspace_id: str,
    *,
    expected_version: int,
) -> dict[str, object]:
    """Mark a terminal workspace cleaned after Rust removes its managed path."""
    cursor = await db.execute(
        """UPDATE task_workspaces
           SET cleaned_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
               updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
               version=version+1
           WHERE id=? AND company_id=? AND version=?
             AND status IN ('applied','abandoned') AND cleaned_at IS NULL""",
        (workspace_id, company_id, expected_version),
    )
    if cursor.rowcount != 1:
        raise ValueError("STATE_TRANSITION_INVALID")
    return {
        "workspace_id": workspace_id,
        "cleaned": True,
        "version": expected_version + 1,
    }


# ── Workspace lifecycle ─────────────────────────────────────────────────────


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def create_workspace(
    db: Any,
    *,
    company_id: str,
    company_task_id: str,
    workspace_grant_id: str,
    repository_root: str,
    baseline_commit_sha: str,
    user_branch_name: str,
    integration_branch_name: str,
    integration_worktree_path: str,
) -> dict[str, Any]:
    """Create a new workspace for a task (J.1/J.2)."""
    ws_id = _id()
    now = _now()

    await db.execute(
        """INSERT INTO task_workspaces
           (id, company_id, company_task_id, workspace_grant_id,
            repository_root, baseline_commit_sha, user_branch_name,
            integration_branch_name, integration_worktree_path,
            status, created_at, updated_at, version)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        (
            ws_id,
            company_id,
            company_task_id,
            workspace_grant_id,
            repository_root,
            baseline_commit_sha,
            user_branch_name,
            integration_branch_name,
            integration_worktree_path,
            "preparing",
            now,
            now,
        ),
    )
    return {
        "workspace_id": ws_id,
        "status": "preparing",
        "created_at": now,
    }


async def open_workspace(
    db: Any,
    company_id: str,
    workspace_id: str,
    *,
    expected_version: int,
) -> TaskWorkspaceResponse:
    """Activate a workspace after git worktrees are ready (J.2)."""
    cursor = await db.execute(
        """UPDATE task_workspaces
           SET status='active',
               updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
               version=version+1
           WHERE id=? AND company_id=? AND version=?
             AND status='preparing'""",
        (workspace_id, company_id, expected_version),
    )
    if cursor.rowcount != 1:
        raise ValueError("STATE_TRANSITION_INVALID")
    return await get_workspace(db, company_id, workspace_id)


async def archive_workspace(
    db: Any,
    company_id: str,
    workspace_id: str,
    *,
    expected_version: int,
) -> TaskWorkspaceResponse:
    """Move a workspace to abandoned terminal state."""
    cursor = await db.execute(
        """UPDATE task_workspaces
           SET status='abandoned',
               updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
               version=version+1
           WHERE id=? AND company_id=? AND version=?
             AND status IN ('preparing','active','ready_to_apply')""",
        (workspace_id, company_id, expected_version),
    )
    if cursor.rowcount != 1:
        raise ValueError("STATE_TRANSITION_INVALID")
    return await get_workspace(db, company_id, workspace_id)


async def apply_workspace(
    db: Any,
    company_id: str,
    workspace_id: str,
    *,
    expected_version: int,
) -> dict[str, Any]:
    """Merge integration branch into user branch (J.3).

    On success: commits merge, sets status to ``applied``.
    On conflict: aborts merge, sets status to ``ready_to_apply`` for manual
    resolution.  Never modifies the user worktree on conflict.
    """
    from ibreeze.workspace.git_ops import get_merge_conflicts, git_command

    ws = await get_workspace(db, company_id, workspace_id)

    if ws.status != "ready_to_apply":
        raise ValueError("STATE_TRANSITION_INVALID")
    if ws.version != expected_version:
        raise ValueError("OPTIMISTIC_LOCK_CONFLICT")

    integration_path = ws.integration_worktree_path
    integration_branch = ws.integration_branch_name

    # Pre-condition: integration worktree must be clean
    status_result = await git_command("status", "--porcelain", cwd=integration_path)
    if not status_result["success"]:
        raise ValueError("WORKSPACE_NOT_FOUND")
    if status_result["stdout"].strip():
        raise ValueError("WORKSPACE_DIRTY")
    integration_branch_result = await git_command(
        "symbolic-ref", "--quiet", "--short", "HEAD", cwd=integration_path
    )
    if not integration_branch_result["success"] or integration_branch_result["stdout"].strip() != integration_branch:
        raise ValueError("WORKSPACE_ACCESS_DENIED")

    # J.3 applies only to the user's unchanged worktree.  Never merge into a
    # path or branch that drifted after plan confirmation.
    user_status_result = await git_command("status", "--porcelain", cwd=ws.repository_root)
    user_branch_result = await git_command(
        "symbolic-ref", "--quiet", "--short", "HEAD", cwd=ws.repository_root
    )
    user_head_result = await git_command("rev-parse", "HEAD", cwd=ws.repository_root)
    if (
        not user_status_result["success"]
        or user_status_result["stdout"].strip()
        or not user_branch_result["success"]
        or user_branch_result["stdout"].strip() != ws.user_branch_name
        or not user_head_result["success"]
        or user_head_result["stdout"].strip() != ws.baseline_commit_sha
    ):
        raise ValueError("WORKSPACE_ACCESS_DENIED")

    # Attempt merge into integration branch (conflict means abort, not apply)
    merge_result = await git_command(
        "merge",
        "--no-ff",
        "--no-commit",
        integration_branch,
        cwd=ws.repository_root,
    )

    _now()
    if merge_result["success"]:
        # Commit the merge
        commit_result = await git_command(
            "commit",
            "-m",
            f"ibreeze({ws.company_task_id[:8]}): apply completed task",
            cwd=ws.repository_root,
        )
        if not commit_result["success"]:
            await git_command("merge", "--abort", cwd=ws.repository_root)
            raise ValueError("COMMIT_FAILED")

        # Record applied commit SHA
        head_result = await git_command("rev-parse", "HEAD", cwd=ws.repository_root)
        applied_sha = head_result["stdout"].strip() if head_result["success"] else ""

        cursor = await db.execute(
            """UPDATE task_workspaces
               SET status='applied', applied_commit_sha=?,
                   updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                   version=version+1
               WHERE id=? AND company_id=? AND version=?""",
            (applied_sha, workspace_id, company_id, expected_version),
        )
        if cursor.rowcount != 1:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
        return {
            "workspace_id": workspace_id,
            "status": "applied",
            "applied_commit_sha": applied_sha,
        }

    # Conflict: abort merge, leave workspace for manual resolution
    conflict_files = await get_merge_conflicts(ws.repository_root)
    await git_command("merge", "--abort", cwd=ws.repository_root)

    # Mark ready for manual apply
    cursor = await db.execute(
        """UPDATE task_workspaces
           SET status='ready_to_apply',
               updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
               version=version+1
           WHERE id=? AND company_id=? AND version=? AND status='ready_to_apply'""",
        (workspace_id, company_id, expected_version),
    )
    if cursor.rowcount != 1:
        raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
    return {
        "workspace_id": workspace_id,
        "status": "ready_to_apply",
        "conflicts": conflict_files,
    }
