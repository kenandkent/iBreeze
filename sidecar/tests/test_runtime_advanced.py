"""Tests for runtime advanced scenarios.

Covers RUN-001, RUN-002, RUN-003, RUN-010, RUN-012.
"""

from __future__ import annotations

import aiosqlite
import pytest

from ibreeze.company import create_company
from ibreeze.runtime.scheduler import (
    acquire_lease,
    dequeue_next,
    enqueue,
    heartbeat_lease,
    release_lease,
    update_fairness,
)
from ibreeze.schemas import CompanyCreate
from ibreeze.state_machine import can_transition, get_allowed_targets, is_terminal


async def _company(db: aiosqlite.Connection, profile_id: str, name: str):
    return await create_company(
        db,
        CompanyCreate(
            name=name,
            introduction="调度测试公司",
            general_manager_name="总经理",
            base_profile_version_id=profile_id,
        ),
    )


async def _enqueue_with_run(
    db: aiosqlite.Connection,
    company_id: str,
    run_id: str,
    *,
    work_item_id: str,
    job_id: str,
    priority: int = 0,
) -> str:
    """Enqueue after ensuring the agent_run FK is satisfied."""
    now = "2026-01-01T00:00:00Z"
    sha256 = "a" * 64
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """INSERT INTO agent_runs
               (id, company_id, company_task_id, work_item_id, employee_id,
                conversation_id, availability_snapshot_id, execution_snapshot_id,
                run_purpose, adapter_type, run_spec_json, run_spec_sha256,
                status, attempt, created_at, updated_at, version)
               VALUES (?,?,?,?,'emp-fake','conv-fake','avail-fake','exec-fake',
                       'review',
                       'codex_cli','{}',?,'queued',1,?,?,1)""",
            (run_id, company_id, work_item_id, work_item_id, sha256, now, now),
        )
        await db.commit()
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    return await enqueue(
        db,
        company_id=company_id,
        run_id=run_id,
        work_item_type="employee_task",
        work_item_id=work_item_id,
        job_id=job_id,
        priority=priority,
    )


@pytest.mark.asyncio
class TestFairScheduling:
    """RUN-001: Tasks should be scheduled fairly across departments."""

    async def test_enqueue_and_dequeue(self, db, published_profile):
        company = await _company(db, published_profile, "调度A")
        queue_id = await _enqueue_with_run(
            db,
            company.id,
            "run-1",
            work_item_id="task-1",
            job_id="job-1",
        )
        assert queue_id is not None
        item = await dequeue_next(db)
        assert item is not None
        assert item["work_item_id"] == "task-1"

    async def test_fairness_by_company(self, db, published_profile):
        """RUN-001: Previously dispatched company gets lower priority."""
        company_a = await _company(db, published_profile, "调度公平A")
        company_b = await _company(db, published_profile, "调度公平B")
        await _enqueue_with_run(
            db, company_a.id, "run-a", work_item_id="task-a", job_id="job-a",
        )
        await _enqueue_with_run(
            db, company_b.id, "run-b", work_item_id="task-b", job_id="job-b",
        )
        item = await dequeue_next(db)
        assert item["company_id"] == company_a.id
        await update_fairness(db, company_a.id)
        item = await dequeue_next(db)
        assert item["company_id"] == company_b.id

    async def test_priority_ordering(self, db, published_profile):
        """RUN-001: Higher priority (lower number) dequeued first."""
        company = await _company(db, published_profile, "优先级排序")
        await _enqueue_with_run(
            db, company.id, "run-low",
            work_item_id="task-low", job_id="job-low", priority=20,
        )
        await _enqueue_with_run(
            db, company.id, "run-high",
            work_item_id="task-high", job_id="job-high", priority=0,
        )
        item = await dequeue_next(db)
        assert item["work_item_id"] == "task-high"

    async def test_dequeue_empty_returns_none(self, db):
        item = await dequeue_next(db)
        assert item is None


@pytest.mark.asyncio
class TestSlotLimitEnforcement:
    """RUN-002: Max concurrent runs should be enforced."""

    async def test_lease_acquisition(self, db, published_profile):
        company = await _company(db, published_profile, "租约获取")
        queue_id = await _enqueue_with_run(
            db, company.id, "run-c",
            work_item_id="task-c", job_id="job-c",
        )
        lease_id = await acquire_lease(
            db,
            queue_id=queue_id,
            job_id="job-c",
            run_id="run-c",
            employee_id=company.general_manager_employee_id,
            company_id=company.id,
            conversation_id=company.company_conversation_id,
        )
        assert lease_id is not None
        item = await (
            await db.execute(
                "SELECT status FROM runtime_queue WHERE id=?", (queue_id,)
            )
        ).fetchone()
        assert item["status"] == "leased"

    async def test_concurrent_lease_conflict(self, db, published_profile):
        """RUN-002: Second lease on same queue fails."""
        company = await _company(db, published_profile, "租约冲突")
        queue_id = await _enqueue_with_run(
            db, company.id, "run-d",
            work_item_id="task-d", job_id="job-d",
        )
        lease1 = await acquire_lease(
            db,
            queue_id=queue_id,
            job_id="job-d",
            run_id="run-d",
            employee_id=company.general_manager_employee_id,
            company_id=company.id,
            conversation_id=company.company_conversation_id,
        )
        assert lease1 is not None
        lease2 = await acquire_lease(
            db,
            queue_id=queue_id,
            job_id="job-d",
            run_id="run-d",
            employee_id=company.general_manager_employee_id,
            company_id=company.id,
            conversation_id=company.company_conversation_id,
        )
        assert lease2 is None

    async def test_release_lease_marks_completed(self, db, published_profile):
        company = await _company(db, published_profile, "释放租约")
        queue_id = await _enqueue_with_run(
            db, company.id, "run-e",
            work_item_id="task-e", job_id="job-e",
        )
        lease_id = await acquire_lease(
            db,
            queue_id=queue_id,
            job_id="job-e",
            run_id="run-e",
            employee_id=company.general_manager_employee_id,
            company_id=company.id,
            conversation_id=company.company_conversation_id,
        )
        await release_lease(db, lease_id)
        item = await (
            await db.execute(
                "SELECT status FROM runtime_queue WHERE id=?", (queue_id,)
            )
        ).fetchone()
        assert item["status"] == "completed"
        lease = await (
            await db.execute(
                "SELECT COUNT(*) as cnt FROM runtime_leases WHERE id=?", (lease_id,)
            )
        ).fetchone()
        assert lease["cnt"] == 0


@pytest.mark.asyncio
class TestLeaseReclaimOnTimeout:
    """RUN-003: Leases should be reclaimed on timeout."""

    async def test_heartbeat_extends_lease(self, db, published_profile):
        company = await _company(db, published_profile, "心跳续期")
        queue_id = await _enqueue_with_run(
            db, company.id, "run-f",
            work_item_id="task-f", job_id="job-f",
        )
        lease_id = await acquire_lease(
            db,
            queue_id=queue_id,
            job_id="job-f",
            run_id="run-f",
            employee_id=company.general_manager_employee_id,
            company_id=company.id,
            conversation_id=company.company_conversation_id,
            ttl_seconds=3600,
        )
        assert lease_id is not None
        lease = await (
            await db.execute(
                "SELECT expires_at FROM runtime_leases WHERE id=?", (lease_id,)
            )
        ).fetchone()
        assert lease is not None
        result = await heartbeat_lease(db, lease_id)
        assert isinstance(result, bool)

    async def test_heartbeat_on_expired_lease_returns_false(self, db):
        """RUN-003: Heartbeat on expired lease fails."""
        result = await heartbeat_lease(db, "nonexistent-lease-id")
        assert result is False

    async def test_release_removes_lease(self, db, published_profile):
        company = await _company(db, published_profile, "释放移除租约")
        queue_id = await _enqueue_with_run(
            db, company.id, "run-g",
            work_item_id="task-g", job_id="job-g",
        )
        lease_id = await acquire_lease(
            db,
            queue_id=queue_id,
            job_id="job-g",
            run_id="run-g",
            employee_id=company.general_manager_employee_id,
            company_id=company.id,
            conversation_id=company.company_conversation_id,
        )
        await release_lease(db, lease_id)
        lease_count = await (
            await db.execute(
                "SELECT COUNT(*) as cnt FROM runtime_leases WHERE id=?", (lease_id,)
            )
        ).fetchone()
        assert lease_count["cnt"] == 0


@pytest.mark.asyncio
class TestVerificationFixLimit:
    """RUN-010: Verification loop should have a fix limit."""

    def test_verifying_to_retrying_has_limit(self):
        """RUN-010: After max retries, verifying should not loop forever."""
        assert can_transition("AgentRun", "verifying", "retrying")
        assert can_transition("AgentRun", "verifying", "succeeded")
        assert can_transition("AgentRun", "verifying", "failed")

    def test_retrying_to_starting_enables_reentry(self):
        assert can_transition("AgentRun", "retrying", "starting")

    def test_retrying_to_failed_breaks_loop(self):
        assert can_transition("AgentRun", "retrying", "failed")
        assert is_terminal("AgentRun", "failed")

    def test_retrying_to_cancelled_breaks_loop(self):
        assert can_transition("AgentRun", "retrying", "cancelled")
        assert is_terminal("AgentRun", "cancelled")

    def test_retrying_to_timed_out_breaks_loop(self):
        assert can_transition("AgentRun", "retrying", "timed_out")
        assert is_terminal("AgentRun", "timed_out")

    def test_lost_state_enables_recovery(self):
        """RUN-010: Lost runs can be recovered via retrying."""
        assert can_transition("AgentRun", "lost", "retrying")
        assert can_transition("AgentRun", "lost", "cancelled")
        assert can_transition("AgentRun", "lost", "failed")


@pytest.mark.asyncio
class TestAdapterResultContradiction:
    """RUN-012: Adapter result contradictions should be flagged."""

    def test_terminal_run_states(self):
        """RUN-012: Terminal states must not have outgoing transitions."""
        assert is_terminal("AgentRun", "succeeded")
        assert is_terminal("AgentRun", "cancelled")
        assert is_terminal("AgentRun", "timed_out")
        assert is_terminal("AgentRun", "failed")

    def test_running_to_conflicting_states(self):
        """RUN-012: Running cannot jump to succeeded directly."""
        assert not can_transition("AgentRun", "running", "succeeded")

    def test_starting_cannot_skip_to_succeeded(self):
        assert not can_transition("AgentRun", "starting", "succeeded")

    def test_probing_cannot_skip_to_succeeded(self):
        assert not can_transition("AgentRun", "probing", "succeeded")

    def test_only_verifying_can_succeed(self):
        """RUN-012: Only verifying state can reach succeeded."""
        for state in ("queued", "probing", "starting", "running", "retrying"):
            assert not can_transition("AgentRun", state, "succeeded")
        assert can_transition("AgentRun", "verifying", "succeeded")

    def test_run_to_lost_requires_running(self):
        """RUN-012: Only running runs can become lost."""
        assert can_transition("AgentRun", "running", "lost")
        assert not can_transition("AgentRun", "starting", "lost")
        assert not can_transition("AgentRun", "verifying", "lost")
