"""Gap coverage for collaboration.py create_subtasks factory (lines 196-205).

The individual strategy creators are covered by test_orchestration_extended.py;
only the ``create_subtasks`` dispatcher remains uncovered.  It must map every
CollaborationStrategy to its creator and reject unknown strategies loudly.
"""

from __future__ import annotations

from typing import Any

import pytest

from ibreeze.orchestration.collaboration import (
    CollaborationStrategy,
    create_subtasks,
)


class TestCreateSubtasksFactory:
    @pytest.mark.asyncio
    async def test_independent_dispatch(self, mock_db_session: Any) -> None:
        subtasks = await create_subtasks(
            CollaborationStrategy.INDEPENDENT,
            db=mock_db_session,
            company_task_id="task-1",
            company_id="comp-1",
            employee_ids=["emp-1", "emp-2"],
            task_input={"prompt": "test"},
        )
        assert len(subtasks) == 2
        assert all(s.strategy == CollaborationStrategy.INDEPENDENT for s in subtasks)

    @pytest.mark.asyncio
    async def test_parallel_merge_dispatch(self, mock_db_session: Any) -> None:
        subtasks = await create_subtasks(
            CollaborationStrategy.PARALLEL_WITH_MERGE,
            db=mock_db_session,
            company_task_id="task-1",
            company_id="comp-1",
            employee_ids=["emp-1", "emp-2"],
            task_input={"prompt": "test"},
            partition_key="module_a",
        )
        assert len(subtasks) == 2
        assert subtasks[0].input_snapshot["partition"] == "module_a"

    @pytest.mark.asyncio
    async def test_primary_peer_review_dispatch(self, mock_db_session: Any) -> None:
        subtasks = await create_subtasks(
            CollaborationStrategy.PRIMARY_WITH_PEER_REVIEW,
            db=mock_db_session,
            company_task_id="task-1",
            company_id="comp-1",
            primary_employee_id="emp-1",
            reviewer_employee_ids=["emp-2", "emp-3"],
            task_input={"prompt": "test"},
        )
        assert len(subtasks) == 3
        assert subtasks[0].employee_id == "emp-1"
        assert subtasks[1].input_snapshot["mode"] == "review"

    @pytest.mark.asyncio
    async def test_sequential_refinement_dispatch(self, mock_db_session: Any) -> None:
        subtasks = await create_subtasks(
            CollaborationStrategy.SEQUENTIAL_REFINEMENT,
            db=mock_db_session,
            company_task_id="task-1",
            company_id="comp-1",
            employee_ids=["emp-1", "emp-2"],
            task_input={"prompt": "test"},
        )
        assert len(subtasks) == 2
        assert subtasks[0].input_snapshot["refinement_round"] == 0
        assert subtasks[1].input_snapshot["refinement_round"] == 1

    @pytest.mark.asyncio
    async def test_unknown_strategy_rejected(self, mock_db_session: Any) -> None:
        with pytest.raises(ValueError, match="Unknown strategy"):
            await create_subtasks("bogus_strategy", db=mock_db_session)
