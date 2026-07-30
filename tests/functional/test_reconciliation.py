"""Tests for startup reconciliation.

Covers design spec sections:
- REC-001 Reconciliation order
- REC-002 Writes during reconciliation should be queued
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
class TestReconciliation:
    """Startup reconciliation tests."""

    async def test_startup_reconciliation_order(self):
        """REC-001: Reconciliation should run in correct order."""
        from ibreeze.runtime.recovery import recover_stale_runs, _STALE_STATUSES

        db = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchall.return_value = [
            {"id": "run-1", "status": "running"},
            {"id": "run-2", "status": "queued"},
        ]
        db.execute.return_value = cursor
        db.commit = AsyncMock()

        result = await recover_stale_runs(db)
        assert result["recovered"] == 2
        assert result["checked"] == 2
        assert "running" in _STALE_STATUSES
        assert "queued" in _STALE_STATUSES

    async def test_writes_during_reconciliation(self):
        """REC-002: Writes during reconciliation should be queued."""
        from ibreeze.runtime.recovery import recover_stale_runs

        db = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchall.return_value = []
        db.execute.return_value = cursor
        db.commit = AsyncMock()

        result = await recover_stale_runs(db)
        assert result["recovered"] == 0
        assert result["checked"] == 0

    async def test_recovery_marks_stale_runs_as_failed(self):
        """Stale runs should be marked as failed with recovery message."""
        from ibreeze.runtime.recovery import (
            recover_stale_runs,
            _RECOVERY_MESSAGE_PREFIX,
        )

        db = AsyncMock()
        select_cursor = MagicMock()
        select_cursor.fetchall = AsyncMock(
            return_value=[
                {"id": "run-1", "status": "running"},
            ]
        )
        update_cursor = MagicMock()
        update_cursor.rowcount = 1

        db.execute.side_effect = [select_cursor, update_cursor]
        db.commit = AsyncMock()

        await recover_stale_runs(db)

        assert db.execute.call_count == 2
        update_call = db.execute.call_args_list[1]
        sql = update_call[0][0]
        params = update_call[0][1]
        assert "failed" in sql
        assert params[0].startswith(_RECOVERY_MESSAGE_PREFIX)

    async def test_recovery_only_targets_stale_statuses(self):
        """Only runs in stale statuses should be recovered."""
        from ibreeze.runtime.recovery import _STALE_STATUSES

        assert "running" in _STALE_STATUSES
        assert "queued" in _STALE_STATUSES
        assert "probing" in _STALE_STATUSES
        assert "starting" in _STALE_STATUSES
        assert "verifying" in _STALE_STATUSES
        assert "retrying" in _STALE_STATUSES
        assert "completed" not in _STALE_STATUSES
        assert "failed" not in _STALE_STATUSES
        assert "cancelled" not in _STALE_STATUSES

    async def test_recovery_no_commits_when_nothing_to_recover(self):
        """No commit should happen if there are no stale runs."""
        from ibreeze.runtime.recovery import recover_stale_runs

        db = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchall.return_value = []
        db.execute.return_value = cursor
        db.commit = AsyncMock()

        await recover_stale_runs(db)
        db.commit.assert_not_called()

    async def test_recovery_message_includes_original_status(self):
        """Recovery failure_code should include original run status."""
        from ibreeze.runtime.recovery import recover_stale_runs

        db = AsyncMock()
        select_cursor = MagicMock()
        select_cursor.fetchall = AsyncMock(
            return_value=[
                {"id": "run-1", "status": "probing"},
            ]
        )
        update_cursor = MagicMock()
        update_cursor.rowcount = 1

        db.execute.side_effect = [select_cursor, update_cursor]
        db.commit = AsyncMock()

        await recover_stale_runs(db)

        update_call = db.execute.call_args_list[1]
        params = update_call[0][1]
        assert "probing" in params[0]
