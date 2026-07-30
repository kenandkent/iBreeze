"""Collaboration strategies for multi-employee task execution."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class CollaborationStrategy(StrEnum):
    INDEPENDENT = "independent"
    PARALLEL_WITH_MERGE = "parallel_with_merge"
    PRIMARY_WITH_PEER_REVIEW = "primary_with_peer_review"
    SEQUENTIAL_REFINEMENT = "sequential_refinement"


@dataclass(frozen=True, slots=True)
class SubTask:
    id: str
    employee_id: str
    strategy: CollaborationStrategy
    input_snapshot: dict[str, Any]
    status: str
    order: int


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def create_independent_subtasks(
    db: Any,
    *,
    company_task_id: str,
    company_id: str,
    employee_ids: list[str],
    task_input: dict[str, Any],
) -> list[SubTask]:
    """Strategy 1: Each employee works independently on full input."""
    subtasks = []
    for idx, employee_id in enumerate(employee_ids):
        subtask_id = _id()
        subtasks.append(
            SubTask(
                id=subtask_id,
                employee_id=employee_id,
                strategy=CollaborationStrategy.INDEPENDENT,
                input_snapshot=task_input,
                status="created",
                order=idx,
            )
        )
        await db.execute(
            """INSERT INTO employee_tasks
               (id, company_id, department_task_id, employee_id, task_kind, objective,
                acceptance_criteria_json, status, resume_state, created_at, updated_at, version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                subtask_id,
                company_id,
                company_task_id,
                employee_id,
                "independent",
                json.dumps(task_input),
                json.dumps([]),
                "pending",
                json.dumps({}),
                _now(),
                _now(),
                1,
            ),
        )
    return subtasks


async def create_parallel_merge_subtasks(
    db: Any,
    *,
    company_task_id: str,
    company_id: str,
    employee_ids: list[str],
    task_input: dict[str, Any],
    partition_key: str,
) -> list[SubTask]:
    """Strategy 2: Parallel work with merge at end."""
    subtasks = []
    for idx, employee_id in enumerate(employee_ids):
        subtask_id = _id()
        partitioned_input = {
            **task_input,
            "partition": partition_key,
            "partition_index": idx,
        }
        subtasks.append(
            SubTask(
                id=subtask_id,
                employee_id=employee_id,
                strategy=CollaborationStrategy.PARALLEL_WITH_MERGE,
                input_snapshot=partitioned_input,
                status="created",
                order=idx,
            )
        )
    return subtasks


async def create_primary_review_subtasks(
    db: Any,
    *,
    company_task_id: str,
    company_id: str,
    primary_employee_id: str,
    reviewer_employee_ids: list[str],
    task_input: dict[str, Any],
) -> list[SubTask]:
    """Strategy 3: Primary worker + peer reviewers."""
    subtasks = []

    primary_id = _id()
    subtasks.append(
        SubTask(
            id=primary_id,
            employee_id=primary_employee_id,
            strategy=CollaborationStrategy.PRIMARY_WITH_PEER_REVIEW,
            input_snapshot=task_input,
            status="created",
            order=0,
        )
    )

    for idx, reviewer_id in enumerate(reviewer_employee_ids):
        review_id = _id()
        subtasks.append(
            SubTask(
                id=review_id,
                employee_id=reviewer_id,
                strategy=CollaborationStrategy.PRIMARY_WITH_PEER_REVIEW,
                input_snapshot={
                    "mode": "review",
                    "primary_subtask_id": primary_id,
                },
                status="created",
                order=idx + 1,
            )
        )

    return subtasks


async def create_sequential_refinement_subtasks(
    db: Any,
    *,
    company_task_id: str,
    company_id: str,
    employee_ids: list[str],
    task_input: dict[str, Any],
) -> list[SubTask]:
    """Strategy 4: Sequential refinement chain."""
    subtasks = []
    previous_output: dict[str, Any] = task_input

    for idx, employee_id in enumerate(employee_ids):
        subtask_id = _id()
        subtasks.append(
            SubTask(
                id=subtask_id,
                employee_id=employee_id,
                strategy=CollaborationStrategy.SEQUENTIAL_REFINEMENT,
                input_snapshot={
                    "original_input": task_input,
                    "previous_output": previous_output,
                    "refinement_round": idx,
                },
                status="created",
                order=idx,
            )
        )
        previous_output = {"subtask_id": subtask_id, "output": None}

    return subtasks


async def create_subtasks(
    strategy: CollaborationStrategy,
    **kwargs: Any,
) -> list[SubTask]:
    """Factory function to create subtasks based on strategy."""
    creators = {
        CollaborationStrategy.INDEPENDENT: create_independent_subtasks,
        CollaborationStrategy.PARALLEL_WITH_MERGE: create_parallel_merge_subtasks,
        CollaborationStrategy.PRIMARY_WITH_PEER_REVIEW: create_primary_review_subtasks,
        CollaborationStrategy.SEQUENTIAL_REFINEMENT: create_sequential_refinement_subtasks,
    }
    creator = creators.get(strategy)
    if creator is None:
        raise ValueError(f"Unknown strategy: {strategy}")
    return await creator(**kwargs)  # type: ignore[no-any-return,operator]
