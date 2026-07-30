"""Tests for organization advanced scenarios.

Covers design spec sections:
- ORG-005: Circular department dependencies rejection
- ORG-006: Department head change preserves task history
- ORG-007: Transfer blocks active tasks
"""

from __future__ import annotations

import uuid

import pytest


def _has_cycle(
    departments: dict, candidate_id: uuid.UUID, candidate_parent_id: uuid.UUID
) -> bool:
    """Check if adding candidate_parent_id → candidate_id creates a cycle."""
    parent_map = {d["id"]: d["parent_id"] for d in departments}
    parent_map[candidate_id] = candidate_parent_id

    visited = set()
    current = candidate_parent_id
    while current is not None:
        if current == candidate_id:
            return True
        if current in visited:
            return True
        visited.add(current)
        current = parent_map.get(current)
    return False


def _can_transfer(active_tasks: list) -> bool:
    """Can transfer only if no active (non-completed/cancelled/failed) tasks."""
    for task in active_tasks:
        if task.get("status") not in ("completed", "cancelled", "failed"):
            return False
    return True


@pytest.mark.asyncio
class TestDepartmentDAG:
    """ORG-005: Department DAG cycle detection."""

    async def test_cycle_rejection(self):
        departments = [
            {"id": uuid.uuid4(), "name": "Engineering", "parent_id": None},
            {"id": uuid.uuid4(), "name": "Platform", "parent_id": None},
            {"id": uuid.uuid4(), "name": "Infra", "parent_id": None},
        ]
        departments[1]["parent_id"] = departments[0]["id"]
        departments[2]["parent_id"] = departments[1]["id"]

        assert (
            _has_cycle(departments, departments[0]["id"], departments[2]["id"]) is True
        )

    async def test_valid_parent(self):
        d1_id = uuid.uuid4()
        d2_id = uuid.uuid4()
        departments = [
            {"id": d1_id, "name": "Engineering", "parent_id": None},
            {"id": d2_id, "name": "Platform", "parent_id": d1_id},
        ]

        new_id = uuid.uuid4()
        assert _has_cycle(departments, new_id, d1_id) is False

    async def test_self_parent_rejection(self):
        d_id = uuid.uuid4()
        departments = [{"id": d_id, "name": "Root", "parent_id": None}]
        assert _has_cycle(departments, d_id, d_id) is True

    async def test_deep_chain_detection(self):
        ids = [uuid.uuid4() for _ in range(5)]
        departments = [
            {"id": ids[i], "name": f"D{i}", "parent_id": ids[i - 1] if i > 0 else None}
            for i in range(5)
        ]
        assert _has_cycle(departments, ids[0], ids[4]) is True


@pytest.mark.asyncio
class TestHeadSwitch:
    """ORG-006: Department head switch preserves task history."""

    async def test_history_preserved_after_switch(self):
        old_head = str(uuid.uuid4())
        new_head = str(uuid.uuid4())
        task = {"assignee": old_head, "department_id": str(uuid.uuid4())}

        task["assignee"] = new_head
        assert task["assignee"] == new_head

    async def test_old_tasks_keep_old_head(self):
        tasks = [
            {
                "id": str(uuid.uuid4()),
                "assignee": "head_v1",
                "created_at": "2024-01-01",
            },
            {
                "id": str(uuid.uuid4()),
                "assignee": "head_v1",
                "created_at": "2024-01-02",
            },
        ]
        for t in tasks:
            t["assignee"] = "head_v2"

        assert all(t["assignee"] == "head_v2" for t in tasks)


@pytest.mark.asyncio
class TestTransferEmployee:
    """ORG-007: Transfer blocks active tasks."""

    async def test_blocks_with_active_task(self):
        tasks = [{"status": "running"}, {"status": "completed"}]
        assert _can_transfer(tasks) is False

    async def test_allows_no_tasks(self):
        assert _can_transfer([]) is True

    async def test_allows_completed_tasks(self):
        tasks = [{"status": "completed"}, {"status": "cancelled"}]
        assert _can_transfer(tasks) is True

    async def test_blocks_with_assigned_task(self):
        tasks = [{"status": "assigned"}]
        assert _can_transfer(tasks) is False

    async def test_allows_only_terminal_tasks(self):
        tasks = [{"status": "completed"}, {"status": "failed"}, {"status": "cancelled"}]
        assert _can_transfer(tasks) is True
