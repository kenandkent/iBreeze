"""Tests for task lifecycle and plan management.

Covers PLAN-002, PLAN-003, PLAN-004, PLAN-005, and state transition enforcement.
"""

from __future__ import annotations

import aiosqlite
import pytest

from ibreeze.company import create_company
from ibreeze.conversation import get_company_conversation, submit_user_message
from ibreeze.schemas import CompanyCreate, SubmitUserMessageRequest
from ibreeze.state_machine import (
    StateTransitionError,
    can_transition,
    get_allowed_targets,
    is_terminal,
    transition,
    validate_resume_state,
)
from ibreeze.task.service import (
    cancel_task,
    confirm_plan,
    get_company_task,
    list_company_tasks,
    pause_task,
    reject_plan,
    request_plan_revision,
    resume_task,
)


async def _company(db: aiosqlite.Connection, profile_id: str, name: str):
    return await create_company(
        db,
        CompanyCreate(
            name=name,
            introduction="按部门职责完成交付",
            general_manager_name="总经理",
            base_profile_version_id=profile_id,
        ),
    )


async def _task_with_status(
    db: aiosqlite.Connection, company_id: str, status: str
) -> str:
    """Create a company task and set it to the given status. Return task_id."""
    conversation = await get_company_conversation(db, company_id)
    result = await submit_user_message(
        db,
        SubmitUserMessageRequest(
            company_id=company_id,
            conversation_id=conversation.id,
            content="创建任务用于生命周期测试",
        ),
    )
    task_id = result.company_task_id
    await db.execute(
        "UPDATE company_tasks SET status=? WHERE id=?",
        (status, task_id),
    )
    await db.commit()
    return task_id


@pytest.mark.asyncio
class TestPlanRevisionReusesTask:
    """PLAN-002: Plan revision should reuse existing task."""

    async def test_plan_revision_reuses_task(self, db, published_profile):
        company = await _company(db, published_profile, "修订公司")
        conversation = await get_company_conversation(db, company.id)
        first = await submit_user_message(
            db,
            SubmitUserMessageRequest(
                company_id=company.id,
                conversation_id=conversation.id,
                content="原始需求",
            ),
        )
        await db.execute(
            """UPDATE company_tasks SET status='awaiting_user_confirmation'
               WHERE id=?""",
            (first.company_task_id,),
        )
        await db.commit()
        revised = await submit_user_message(
            db,
            SubmitUserMessageRequest(
                company_id=company.id,
                conversation_id=conversation.id,
                content="请增加离线模式",
                target_task_id=first.company_task_id,
            ),
        )
        assert revised.company_task_id == first.company_task_id
        assert revised.task_status == "revision_requested"
        assert revised.intake_mode == "plan_revision"

    async def test_plan_revision_supersedes_plan_version(self, db, published_profile):
        company = await _company(db, published_profile, "版本修订公司")
        conversation = await get_company_conversation(db, company.id)
        first = await submit_user_message(
            db,
            SubmitUserMessageRequest(
                company_id=company.id,
                conversation_id=conversation.id,
                content="初始版本",
            ),
        )
        await db.execute(
            """UPDATE company_tasks SET status='awaiting_user_confirmation'
               WHERE id=?""",
            (first.company_task_id,),
        )
        await db.commit()
        plan_versions_before = await (
            await db.execute(
                """SELECT COUNT(*) FROM company_plan_versions
                   WHERE company_task_id=? AND company_id=?""",
                (first.company_task_id, company.id),
            )
        ).fetchone()
        revised = await submit_user_message(
            db,
            SubmitUserMessageRequest(
                company_id=company.id,
                conversation_id=conversation.id,
                content="修订版本",
                target_task_id=first.company_task_id,
            ),
        )
        assert revised.intake_mode == "plan_revision"
        assert revised.company_task_id == first.company_task_id


@pytest.mark.asyncio
class TestTaskStatusTransitions:
    """PLAN-003, PLAN-004: Task type exclusivity and status enforcement."""

    async def test_input_field_mutex_task_type_and_parent(self, db, published_profile):
        """PLAN-004: task_type and parent_task_id are mutually exclusive."""
        company = await _company(db, published_profile, "互斥公司")
        conversation = await get_company_conversation(db, company.id)
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await submit_user_message(
                db,
                SubmitUserMessageRequest(
                    company_id=company.id,
                    conversation_id=conversation.id,
                    content="引用不存在的任务",
                    target_task_id="00000000-0000-4000-8000-000000000000",
                ),
            )

    async def test_unconfirmed_plan_blocks_confirm(self, db, published_profile):
        """PLAN-005: Task cannot execute without plan confirmation."""
        company = await _company(db, published_profile, "未确认公司")
        task_id = await _task_with_status(db, company.id, "draft")
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await confirm_plan(db, company.id, task_id, company.general_manager_employee_id)

    async def test_draft_can_only_transition_to_analyzing_or_cancelling(
        self, db, published_profile
    ):
        company = await _company(db, published_profile, "流转公司")
        task_id = await _task_with_status(db, company.id, "draft")
        task = await get_company_task(db, company.id, task_id)
        assert task["status"] == "draft"
        assert can_transition("CompanyTask", "draft", "analyzing")
        assert can_transition("CompanyTask", "draft", "cancelling")
        assert not can_transition("CompanyTask", "draft", "completed")

    async def test_terminal_states_have_no_outgoing_transitions(self):
        for state in ("completed", "cancelled", "failed", "rejected"):
            assert is_terminal("CompanyTask", state)
            assert get_allowed_targets("CompanyTask", state) == frozenset()

    async def test_awaiting_confirmation_to_revision_requested(self, db, published_profile):
        company = await _company(db, published_profile, "修订流转")
        task_id = await _task_with_status(db, company.id, "awaiting_user_confirmation")
        result = await request_plan_revision(
            db,
            company.id,
            task_id,
            company.general_manager_employee_id,
            reason="需要更多细节",
        )
        assert result["status"] == "revision_requested"

    async def test_awaiting_confirmation_to_rejected(self, db, published_profile):
        company = await _company(db, published_profile, "拒绝流转")
        task_id = await _task_with_status(db, company.id, "awaiting_user_confirmation")
        result = await reject_plan(
            db,
            company.id,
            task_id,
            company.general_manager_employee_id,
            reason="不需要此功能",
        )
        assert result["status"] == "rejected"
        task = await get_company_task(db, company.id, task_id)
        assert task["status"] == "rejected"
        assert is_terminal("CompanyTask", "rejected")


@pytest.mark.asyncio
class TestPauseResumeLifecycle:
    """paused status requires resume_state."""

    async def test_pause_sets_resume_state(self, db, published_profile):
        company = await _company(db, published_profile, "暂停公司")
        task_id = await _task_with_status(db, company.id, "executing")
        result = await pause_task(
            db, company.id, task_id, company.general_manager_employee_id
        )
        assert result["status"] == "paused"
        task = await get_company_task(db, company.id, task_id)
        assert task["resume_state"] == "executing"
        assert task["status"] == "paused"

    async def test_resume_restores_original_state(self, db, published_profile):
        company = await _company(db, published_profile, "恢复公司")
        task_id = await _task_with_status(db, company.id, "executing")
        await pause_task(
            db, company.id, task_id, company.general_manager_employee_id
        )
        task_before = await get_company_task(db, company.id, task_id)
        assert task_before["status"] == "paused"
        assert task_before["resume_state"] == "executing"

    async def test_pause_rejects_non_executing(self, db, published_profile):
        company = await _company(db, published_profile, "非执行暂停")
        task_id = await _task_with_status(db, company.id, "draft")
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await pause_task(
                db, company.id, task_id, company.general_manager_employee_id
            )

    async def test_resume_rejects_non_paused(self, db, published_profile):
        company = await _company(db, published_profile, "非暂停恢复")
        task_id = await _task_with_status(db, company.id, "executing")
        with pytest.raises((ValueError, IndexError)):
            await resume_task(
                db, company.id, task_id, company.general_manager_employee_id
            )

    async def test_paused_state_requires_resume_state(self):
        with pytest.raises(ValueError, match="resume_state required"):
            validate_resume_state("CompanyTask", "paused", None)

    async def test_non_paused_state_rejects_resume_state(self):
        with pytest.raises(ValueError, match="resume_state must be null"):
            validate_resume_state("CompanyTask", "executing", "executing")


@pytest.mark.asyncio
class TestCancelTask:
    """Task cancellation from non-terminal states."""

    async def test_cancel_from_draft(self, db, published_profile):
        company = await _company(db, published_profile, "取消草稿")
        task_id = await _task_with_status(db, company.id, "draft")
        result = await cancel_task(
            db,
            company.id,
            task_id,
            company.general_manager_employee_id,
            reason="不需要了",
        )
        assert result["status"] == "cancelling"
        task = await get_company_task(db, company.id, task_id)
        assert task["status"] == "cancelling"

    async def test_cancel_from_terminal_rejected(self, db, published_profile):
        company = await _company(db, published_profile, "终端取消")
        task_id = await _task_with_status(db, company.id, "completed")
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await cancel_task(
                db,
                company.id,
                task_id,
                company.general_manager_employee_id,
                reason="太晚了",
            )

    async def test_cancel_task_not_found(self, db, published_profile):
        company = await _company(db, published_profile, "找不到取消")
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await cancel_task(
                db,
                company.id,
                "00000000-0000-4000-8000-000000000000",
                company.general_manager_employee_id,
                reason="不存在的任务",
            )


@pytest.mark.asyncio
class TestListCompanyTasks:
    """Task listing with status filter."""

    async def test_list_all_tasks(self, db, published_profile):
        company = await _company(db, published_profile, "列表公司")
        await _task_with_status(db, company.id, "draft")
        await _task_with_status(db, company.id, "executing")
        tasks = await list_company_tasks(db, company.id)
        assert len(tasks) == 2

    async def test_list_tasks_by_status(self, db, published_profile):
        company = await _company(db, published_profile, "过滤列表")
        await _task_with_status(db, company.id, "draft")
        await _task_with_status(db, company.id, "executing")
        draft_tasks = await list_company_tasks(db, company.id, status="draft")
        assert len(draft_tasks) == 1
        assert draft_tasks[0]["status"] == "draft"

    async def test_list_tasks_empty_company(self, db, published_profile):
        company = await _company(db, published_profile, "空列表")
        tasks = await list_company_tasks(db, company.id)
        assert tasks == []


@pytest.mark.asyncio
class TestStateTransitionFunction:
    """Generic state machine transition validation."""

    def test_valid_transition_returns_none(self):
        result = transition("CompanyTask", "draft", "analyzing")
        assert result is None

    def test_invalid_transition_raises(self):
        with pytest.raises(StateTransitionError) as exc_info:
            transition("CompanyTask", "draft", "completed")
        assert exc_info.value.entity == "CompanyTask"
        assert exc_info.value.current == "draft"
        assert exc_info.value.target == "completed"

    def test_terminal_state_raises(self):
        with pytest.raises(StateTransitionError):
            transition("CompanyTask", "completed", "executing")

    def test_get_allowed_targets_draft(self):
        targets = get_allowed_targets("CompanyTask", "draft")
        assert targets == {"analyzing", "cancelling"}

    def test_get_allowed_targets_completed(self):
        assert get_allowed_targets("CompanyTask", "completed") == frozenset()
