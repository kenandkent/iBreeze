"""TaskWorkspace state transitions backed by SQLite."""

from __future__ import annotations

from datetime import datetime
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
        await db.rollback()
        raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
    await db.commit()
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
        await db.rollback()
        raise ValueError("STATE_TRANSITION_INVALID")
    await db.commit()
    return {
        "workspace_id": workspace_id,
        "cleaned": True,
        "version": expected_version + 1,
    }
