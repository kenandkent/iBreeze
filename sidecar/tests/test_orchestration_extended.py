"""Tests for orchestration modules."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ibreeze.orchestration.availability_checker import (
    AvailabilityReport,
    CheckStatus,
    check_concurrency_slot,
    check_health,
    check_workspace,
    run_availability_checks,
)
from ibreeze.orchestration.collaboration import (
    CollaborationStrategy,
    create_independent_subtasks,
    create_parallel_merge_subtasks,
    create_primary_review_subtasks,
    create_sequential_refinement_subtasks,
)
from ibreeze.orchestration.workflow_templates import (
    SOFTWARE_REQUIREMENT_DELIVERY,
    WorkflowPhase,
    WorkflowStep,
    get_next_steps,
    get_workflow_template,
    list_workflow_templates,
)


class TestAvailabilityChecker:
    """Tests for availability checker."""

    @pytest.mark.asyncio
    async def test_check_health(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchone=AsyncMock(return_value={"1": 1})
        ))
        result = await check_health(mock_db_session, company_id="comp-1")
        assert result.status == CheckStatus.PASS

    @pytest.mark.asyncio
    async def test_check_health_failure(self, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=Exception("DB error"))
        result = await check_health(mock_db_session, company_id="comp-1")
        assert result.status == CheckStatus.FAIL

    @pytest.mark.asyncio
    async def test_check_workspace(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchone=AsyncMock(return_value={"cnt": 2})
        ))
        result = await check_workspace(mock_db_session, company_id="comp-1")
        assert result.status == CheckStatus.PASS
        assert "2 workspace(s)" in result.message

    @pytest.mark.asyncio
    async def test_check_workspace_none_available(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchone=AsyncMock(return_value={"cnt": 0})
        ))
        result = await check_workspace(mock_db_session, company_id="comp-1")
        assert result.status == CheckStatus.FAIL

    @pytest.mark.asyncio
    async def test_check_concurrency_slot(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchone=AsyncMock(return_value={"cnt": 2})
        ))
        result = await check_concurrency_slot(
            mock_db_session,
            company_id="comp-1",
            max_concurrent=5,
        )
        assert result.status == CheckStatus.PASS
        assert "3 slot(s) available" in result.message

    @pytest.mark.asyncio
    async def test_check_concurrency_slot_full(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchone=AsyncMock(return_value={"cnt": 5})
        ))
        result = await check_concurrency_slot(
            mock_db_session,
            company_id="comp-1",
            max_concurrent=5,
        )
        assert result.status == CheckStatus.FAIL

    @pytest.mark.asyncio
    async def test_run_availability_checks(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchone=AsyncMock(return_value={"cnt": 2})
        ))
        result = await run_availability_checks(
            mock_db_session,
            company_id="comp-1",
        )
        assert isinstance(result, AvailabilityReport)
        assert result.all_passed is True


class TestCollaboration:
    """Tests for collaboration strategies."""

    @pytest.mark.asyncio
    async def test_independent_subtasks(self, mock_db_session):
        subtasks = await create_independent_subtasks(
            mock_db_session,
            company_task_id="task-1",
            company_id="comp-1",
            employee_ids=["emp-1", "emp-2"],
            task_input={"prompt": "test"},
        )
        assert len(subtasks) == 2
        assert subtasks[0].strategy == CollaborationStrategy.INDEPENDENT
        assert subtasks[0].employee_id == "emp-1"
        assert subtasks[1].employee_id == "emp-2"

    @pytest.mark.asyncio
    async def test_parallel_merge_subtasks(self, mock_db_session):
        subtasks = await create_parallel_merge_subtasks(
            mock_db_session,
            company_task_id="task-1",
            company_id="comp-1",
            employee_ids=["emp-1", "emp-2"],
            task_input={"prompt": "test"},
            partition_key="module_a",
        )
        assert len(subtasks) == 2
        assert subtasks[0].strategy == CollaborationStrategy.PARALLEL_WITH_MERGE
        assert subtasks[0].input_snapshot["partition"] == "module_a"

    @pytest.mark.asyncio
    async def test_primary_review_subtasks(self, mock_db_session):
        subtasks = await create_primary_review_subtasks(
            mock_db_session,
            company_task_id="task-1",
            company_id="comp-1",
            primary_employee_id="emp-1",
            reviewer_employee_ids=["emp-2", "emp-3"],
            task_input={"prompt": "test"},
        )
        assert len(subtasks) == 3
        assert subtasks[0].strategy == CollaborationStrategy.PRIMARY_WITH_PEER_REVIEW
        assert subtasks[0].employee_id == "emp-1"
        assert subtasks[1].input_snapshot["mode"] == "review"

    @pytest.mark.asyncio
    async def test_sequential_refinement_subtasks(self, mock_db_session):
        subtasks = await create_sequential_refinement_subtasks(
            mock_db_session,
            company_task_id="task-1",
            company_id="comp-1",
            employee_ids=["emp-1", "emp-2"],
            task_input={"prompt": "test"},
        )
        assert len(subtasks) == 2
        assert subtasks[0].strategy == CollaborationStrategy.SEQUENTIAL_REFINEMENT
        assert subtasks[0].input_snapshot["refinement_round"] == 0
        assert subtasks[1].input_snapshot["refinement_round"] == 1


class TestWorkflowTemplates:
    """Tests for workflow templates."""

    def test_get_workflow_template(self):
        template = get_workflow_template("software_requirement_delivery")
        assert template is not None
        assert template.name == "software_requirement_delivery"

    def test_get_workflow_template_not_found(self):
        template = get_workflow_template("nonexistent")
        assert template is None

    def test_list_workflow_templates(self):
        templates = list_workflow_templates()
        assert len(templates) >= 1

    def test_get_next_steps_initial(self):
        steps = get_next_steps(SOFTWARE_REQUIREMENT_DELIVERY, set())
        assert len(steps) == 1
        assert steps[0].phase == WorkflowPhase.ANALYSIS

    def test_get_next_steps_after_analysis(self):
        steps = get_next_steps(
            SOFTWARE_REQUIREMENT_DELIVERY,
            {WorkflowPhase.ANALYSIS},
        )
        assert any(s.phase == WorkflowPhase.ARCHITECTURE for s in steps)

    def test_workflow_step_dependencies(self):
        for step in SOFTWARE_REQUIREMENT_DELIVERY.steps:
            assert isinstance(step, WorkflowStep)
            assert step.phase is not None
            assert step.name is not None
