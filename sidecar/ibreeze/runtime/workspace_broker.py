"""Workspace isolation and allocation for task execution."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Status values mirror the DDL CHECK constraint on task_workspaces.status.
_STATUS_PREPARING = "preparing"
_STATUS_ACTIVE = "active"
_STATUS_READY_TO_APPLY = "ready_to_apply"
_STATUS_APPLIED = "applied"
_STATUS_ABANDONED = "abandoned"


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def allocate_workspace(
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
    """Allocate a workspace for a task.

    Creates a ``task_workspaces`` row in ``preparing`` status and ensures the
    integration worktree directory exists on disk.
    """
    ws_id = _id()
    now = _now()

    await db.execute(
        (
            "INSERT INTO task_workspaces "
            "(id, company_id, company_task_id, workspace_grant_id, "
            " repository_root, baseline_commit_sha, user_branch_name, "
            " integration_branch_name, integration_worktree_path, "
            " status, created_at, updated_at, version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)"
        ),
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
            _STATUS_PREPARING,
            now,
            now,
        ),
    )
    await db.commit()

    Path(integration_worktree_path).mkdir(parents=True, exist_ok=True)

    return {
        "workspace_id": ws_id,
        "path": integration_worktree_path,
        "status": _STATUS_PREPARING,
        "created_at": now,
    }


async def activate_workspace(db: Any, workspace_id: str) -> dict[str, Any]:
    """Mark workspace as active."""
    now = _now()
    await db.execute(
        "UPDATE task_workspaces SET status = ?, updated_at = ?, version = version + 1 WHERE id = ?",
        (_STATUS_ACTIVE, now, workspace_id),
    )
    await db.commit()
    return {"workspace_id": workspace_id, "status": _STATUS_ACTIVE, "activated_at": now}


async def get_workspace_path(db: Any, workspace_id: str) -> str | None:
    """Get the filesystem path for a workspace."""
    cursor = await db.execute(
        "SELECT integration_worktree_path FROM task_workspaces WHERE id = ?",
        (workspace_id,),
    )
    row = await cursor.fetchone()
    return row["integration_worktree_path"] if row else None


async def execute_external_write(
    rpc: Any,
    *,
    approval_id: str,
    run_id: str,
    operation: str,
    target_realpath: str,
    expected_old_sha256: str | None = None,
    source_relative_path: str | None = None,
    source_sha256: str | None = None,
    source_size: int | None = None,
    expires_at: str,
) -> dict[str, object]:
    """Execute an external write via reverse RPC to the Rust side.

    Creates an ``ExternalWriteRequest``, sends it via reverse RPC, waits for
    the response, and returns the result (which includes the receipt).
    """
    request = {
        "approval_id": approval_id,
        "run_id": run_id,
        "operation": operation,
        "target_realpath": target_realpath,
        "expected_old_sha256": expected_old_sha256,
        "source_relative_path": source_relative_path,
        "source_sha256": source_sha256,
        "source_size": source_size,
        "expires_at": expires_at,
    }
    response = await rpc.call("host.externalWrite.execute", request)
    return response  # type: ignore[no-any-return]
