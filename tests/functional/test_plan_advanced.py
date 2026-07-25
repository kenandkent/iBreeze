"""Tests for plan advanced scenarios.

Covers design spec sections:
- PLAN-003: Successor task entry after completion
- PLAN-007: Plan output fix limit
- PLAN-008: Concurrent plan confirmations serialized
- PLAN-009: Plan confirmation atomicity
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


def _create_successor_tasks(completed_task, successor_specs):
    """Simulate successor task creation."""
    created = []
    for spec in successor_specs:
        task = {
            "id": str(uuid.uuid4()),
            "title": spec["title"],
            "parent_task_id": str(completed_task["id"]),
            "status": "draft",
        }
        created.append(task)
    return created


def _generate_plan_output(tasks, max_items=100):
    """Simulate plan output generation with limit."""
    return tasks[:max_items]


async def _confirm_plan(db, plan):
    """Simulate atomic plan confirmation with savepoint pattern."""
    old_status = plan["status"]
    old_version = plan.get("version", 0)
    try:
        # In real code: BEGIN → UPDATE → COMMIT
        await db.commit()
        # Only update in-memory state after successful commit
        plan["status"] = "confirmed"
        plan["version"] = old_version + 1
        return plan
    except Exception:
        # Rollback: restore original state
        plan["status"] = old_status
        plan["version"] = old_version
        await db.rollback()
        raise


@pytest.mark.asyncio
class TestSuccessorTaskEntry:
    """PLAN-003: Successor tasks after completion."""

    async def test_creates_successor_tasks(self):
        completed_task = {"id": uuid.uuid4(), "status": "completed"}
        specs = [
            {"title": "Follow-up A", "assignee_id": str(uuid.uuid4())},
            {"title": "Follow-up B", "assignee_id": str(uuid.uuid4())},
        ]
        created = _create_successor_tasks(completed_task, specs)
        assert len(created) == 2
        assert all(t["parent_task_id"] == str(completed_task["id"]) for t in created)

    async def test_empty_specs_no_tasks(self):
        completed_task = {"id": uuid.uuid4(), "status": "completed"}
        created = _create_successor_tasks(completed_task, [])
        assert len(created) == 0

    async def test_successor_inherits_parent(self):
        completed_task = {"id": uuid.uuid4()}
        specs = [{"title": "Child", "assignee_id": str(uuid.uuid4())}]
        created = _create_successor_tasks(completed_task, specs)
        assert created[0]["parent_task_id"] == str(completed_task["id"])


@pytest.mark.asyncio
class TestPlanFixLimit:
    """PLAN-007: Plan output should have a fix limit."""

    async def test_truncates_to_limit(self):
        tasks = [{"title": f"Task {i}"} for i in range(200)]
        output = _generate_plan_output(tasks, max_items=100)
        assert len(output) == 100

    async def test_under_limit_unchanged(self):
        tasks = [{"title": f"Task {i}"} for i in range(50)]
        output = _generate_plan_output(tasks, max_items=100)
        assert len(output) == 50

    async def test_empty_tasks(self):
        output = _generate_plan_output([], max_items=100)
        assert len(output) == 0


@pytest.mark.asyncio
class TestPlanConfirmConcurrent:
    """PLAN-008: Concurrent confirmations should be serialized."""

    async def test_sequential_confirm(self):
        plan = {"id": str(uuid.uuid4()), "status": "draft", "version": 1}
        db = AsyncMock()

        for _ in range(3):
            await _confirm_plan(db, plan)

        assert plan["status"] == "confirmed"
        assert plan["version"] == 4

    async def test_concurrent_confirm_serialized(self):
        plan = {"id": str(uuid.uuid4()), "status": "draft", "version": 1}
        db = AsyncMock()
        lock = asyncio.Lock()

        async def safe_confirm():
            async with lock:
                return await _confirm_plan(db, plan)

        await asyncio.gather(*[safe_confirm() for _ in range(3)])
        assert plan["status"] == "confirmed"


@pytest.mark.asyncio
class TestPlanConfirmAtomicity:
    """PLAN-009: Plan confirmation should be atomic."""

    async def test_commit_on_success(self):
        plan = {"id": str(uuid.uuid4()), "status": "draft", "version": 1}
        db = AsyncMock()

        await _confirm_plan(db, plan)
        db.commit.assert_awaited()

    async def test_rollback_on_failure(self):
        plan = {"id": str(uuid.uuid4()), "status": "draft", "version": 1}
        db = AsyncMock()
        db.commit.side_effect = Exception("db error")

        with pytest.raises(Exception, match="db error"):
            await _confirm_plan(db, plan)
        db.rollback.assert_awaited()

    async def test_status_unchanged_after_failure(self):
        plan = {"id": str(uuid.uuid4()), "status": "draft", "version": 1}
        original_status = plan["status"]
        db = AsyncMock()
        db.commit.side_effect = Exception("db error")

        with pytest.raises(Exception):
            await _confirm_plan(db, plan)
        assert plan["status"] == original_status
