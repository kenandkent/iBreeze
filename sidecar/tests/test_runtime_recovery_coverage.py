"""Coverage tests for ibreeze/runtime/recovery.py (uncovered branches)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from ibreeze.runtime.recovery import (
    cleanup_expired_health,
    reconcile_interrupted_routing,
    reconcile_startup_state,
    recover_stale_runs,
)


def _sha256(data: str) -> str:
    import hashlib

    return hashlib.sha256(data.encode()).hexdigest()


class _Row(dict):
    pass


class _Cursor:
    def __init__(self, rows=None, rowcount: int = 1):
        self._rows = rows or []
        self.rowcount = rowcount

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return self._rows


class _FakeDb:
    """Deterministic fake db returning a scripted cursor per execute call."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def execute(self, sql, parameters=()):
        self.calls.append(sql)
        if self._responses:
            return self._responses.pop(0)
        return _Cursor(rowcount=1)


def _stale_run_row(status: str = "running") -> _Row:
    return _Row(id="run-1", company_id="company-1", status=status, version=1)


@pytest.mark.asyncio
class TestRecoverStaleRuns:
    async def test_rowcount_zero_skips(self):
        # The UPDATE matches nothing -> the run must be skipped (no queue
        # update, no event, not counted).
        fake_db = _FakeDb(
            [
                _Cursor([_stale_run_row()]),
                _Cursor(rowcount=0),
            ]
        )
        result = await recover_stale_runs(fake_db)
        assert result == {"recovered": 0, "checked": 1}

    async def test_recovery_writes_event_when_company_exists(self):
        fake_db = _FakeDb(
            [
                _Cursor([_stale_run_row()]),
                _Cursor(rowcount=1),  # UPDATE agent_runs
                _Cursor(rowcount=1),  # UPDATE runtime_queue
                _Cursor(rowcount=1),  # DELETE runtime_leases
                _Cursor([_Row()]),  # company exists -> event written
            ]
        )
        with patch("ibreeze.runtime.run_executor._write_event", new=AsyncMock()) as write_event:
            result = await recover_stale_runs(fake_db)
        assert result == {"recovered": 1, "checked": 1}
        write_event.assert_awaited_once()

    async def test_recovery_skips_event_when_company_missing(self):
        fake_db = _FakeDb(
            [
                _Cursor([_stale_run_row(status="queued")]),
                _Cursor(rowcount=1),  # UPDATE agent_runs
                _Cursor(rowcount=1),  # UPDATE runtime_queue
                _Cursor(rowcount=1),  # DELETE runtime_leases
                _Cursor(rows=[]),  # company missing -> no event
            ]
        )
        with patch("ibreeze.runtime.run_executor._write_event", new=AsyncMock()) as write_event:
            result = await recover_stale_runs(fake_db)
        assert result == {"recovered": 1, "checked": 1}
        write_event.assert_not_awaited()


@pytest.mark.asyncio
class TestCleanupExpiredHealth:
    async def test_deletes_only_expired_ready_rows(self, db):
        now = "2026-01-02T00:00:00Z"
        expired = "2026-01-01T00:00:00Z"
        future = "2026-03-01T00:00:00Z"
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            for idx, (state, benched) in enumerate(
                [("ready", expired), ("ready", future), ("credential_invalid", expired)]
            ):
                await db.execute(
                    """INSERT INTO deployment_health
                       (company_id, provider_release_id, model_binding_id, credential_ref_sha256,
                        availability_state, consecutive_strikes, benched_until, updated_at)
                       VALUES (?, 'rel', 'bind', ?, ?, 0, ?, ?)""",
                    (f"company-{idx}", _sha256(f"{idx}"), state, benched, now),
                )
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        await db.commit()
        deleted = await cleanup_expired_health(db, now=now)
        assert deleted == 1
        remaining = await (await db.execute("SELECT company_id FROM deployment_health")).fetchall()
        assert {r["company_id"] for r in remaining} == {"company-1", "company-2"}

    async def test_default_now_param(self, db):
        deleted = await cleanup_expired_health(db)
        assert isinstance(deleted, int)


@pytest.mark.asyncio
class TestReconcileInterruptedRouting:
    async def test_fail_attempts_without_active_set(self):
        fake_db = _FakeDb(
            [
                _Cursor([_Row(id="a-1", route_decision_id="d-1", status="streaming")]),
                _Cursor(rowcount=1),  # UPDATE attempt -> failed
                _Cursor(rowcount=1),  # UPDATE planned decisions -> failed
                _Cursor([_Row(id="d-1"), _Row(id="d-2")]),  # executing decisions
                _Cursor(rowcount=1),  # UPDATE executing d-1
                _Cursor(rowcount=1),  # UPDATE executing d-2
            ]
        )
        result = await reconcile_interrupted_routing(fake_db)
        assert result["failed_attempts"] == 1
        assert result["preserved_attempts"] == 0
        assert result["failed_planned_decisions"] == 1
        assert result["failed_executing_decisions"] == 2

    async def test_preserve_active_attempts(self):
        fake_db = _FakeDb(
            [
                _Cursor([_Row(id="a-1", route_decision_id="d-1", status="streaming")]),
                _Cursor(rowcount=1),  # UPDATE planned decisions -> failed
                _Cursor([_Row(id="d-1")]),  # executing decision
                _Cursor([_Row()]),  # active attempt still streaming -> preserved
            ]
        )
        result = await reconcile_interrupted_routing(fake_db, active_attempt_ids=["a-1"])
        assert result["failed_attempts"] == 0
        assert result["preserved_attempts"] == 1
        assert result["failed_planned_decisions"] == 1
        assert result["failed_executing_decisions"] == 0

    async def test_executing_decision_failed_when_no_matching_active_attempt(self):
        fake_db = _FakeDb(
            [
                _Cursor([]),  # no stale attempts
                _Cursor(rowcount=0),  # no planned decisions
                _Cursor([_Row(id="d-1")]),  # executing decision
                _Cursor(rowcount=1),  # UPDATE executing d-1 -> failed
            ]
        )
        result = await reconcile_interrupted_routing(fake_db, active_attempt_ids=[])
        assert result["failed_executing_decisions"] == 1


@pytest.mark.asyncio
async def test_reconcile_startup_state_composes(db):
    with (
        patch("ibreeze.runtime.recovery.recover_stale_runs", new=AsyncMock(return_value={"recovered": 0, "checked": 0})),
        patch(
            "ibreeze.runtime.recovery.reconcile_interrupted_routing",
            new=AsyncMock(return_value={"failed_attempts": 0}),
        ),
        patch("ibreeze.runtime.recovery.cleanup_expired_health", new=AsyncMock(return_value=0)),
    ):
        result = await reconcile_startup_state(db)
    assert result == {
        "runs": {"recovered": 0, "checked": 0},
        "routing": {"failed_attempts": 0},
        "expired_health": 0,
    }
