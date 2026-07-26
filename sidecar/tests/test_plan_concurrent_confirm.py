"""PLAN-008: Concurrent plan confirmation tests.

Tests that plan confirmation only succeeds when the task is in the correct state,
and that stale state transitions are rejected (simulating concurrency via sequential calls).
"""

from __future__ import annotations

import uuid

import aiosqlite
import pytest

from ibreeze.company import create_company
from ibreeze.conversation import get_company_conversation, submit_user_message
from ibreeze.schemas import CompanyCreate, SubmitUserMessageRequest
from ibreeze.task.service import confirm_plan, get_company_task


async def _company(db: aiosqlite.Connection, profile_id: str, name: str):
    return await create_company(
        db,
        CompanyCreate(
            name=name,
            introduction="并发测试公司",
            general_manager_name="总经理",
            base_profile_version_id=profile_id,
        ),
    )


async def _task_with_plan(
    db: aiosqlite.Connection, company_id: str
) -> tuple[str, str]:
    """Create a task with awaiting_user_confirmation status. Return (task_id, plan_id)."""
    conversation = await get_company_conversation(db, company_id)
    result = await submit_user_message(
        db,
        SubmitUserMessageRequest(
            company_id=company_id,
            conversation_id=conversation.id,
            content="并发确认测试任务",
        ),
    )
    task_id = result.company_task_id
    await db.execute(
        "UPDATE company_tasks SET status='awaiting_user_confirmation' WHERE id=?",
        (task_id,),
    )
    plan_id = str(uuid.uuid4())
    now = "2026-01-01T00:00:00Z"
    await db.execute(
        """INSERT INTO company_plan_versions
           (id, company_task_id, company_id, version_number, canonical_json,
            content_sha256, generated_by_run_id, status, created_at)
           VALUES (?, ?, ?, 1, '{}', ?, 'run-fake', 'awaiting_user_confirmation', ?)""",
        (plan_id, task_id, company_id, "a" * 64, now),
    )
    await db.commit()
    return task_id, plan_id


@pytest.mark.asyncio
class TestPlanConfirmationGuard:
    """PLAN-008: Plan confirmation only succeeds from correct state."""

    async def test_first_confirm_succeeds(self, db, published_profile):
        company = await _company(db, published_profile, "首次确认")
        task_id, _ = await _task_with_plan(db, company.id)
        result = await confirm_plan(
            db, company.id, task_id, company.general_manager_employee_id
        )
        assert result["status"] == "approved"

    async def test_second_confirm_rejected(self, db, published_profile):
        company = await _company(db, published_profile, "重复确认")
        task_id, _ = await _task_with_plan(db, company.id)
        await confirm_plan(
            db, company.id, task_id, company.general_manager_employee_id
        )
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await confirm_plan(
                db, company.id, task_id, company.general_manager_employee_id
            )

    async def test_confirm_nonexistent_task_fails(self, db, published_profile):
        company = await _company(db, published_profile, "不存在任务")
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await confirm_plan(
                db,
                company.id,
                "00000000-0000-4000-8000-000000000000",
                company.general_manager_employee_id,
            )

    async def test_confirm_wrong_status_fails(self, db, published_profile):
        company = await _company(db, published_profile, "错误状态")
        conversation = await get_company_conversation(db, company.id)
        result = await submit_user_message(
            db,
            SubmitUserMessageRequest(
                company_id=company.id,
                conversation_id=conversation.id,
                content="测试任务",
            ),
        )
        task = await get_company_task(db, company.id, result.company_task_id)
        assert task["status"] == "draft"

        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await confirm_plan(
                db,
                company.id,
                result.company_task_id,
                company.general_manager_employee_id,
            )

    async def test_task_approved_after_confirm(self, db, published_profile):
        company = await _company(db, published_profile, "确认后状态")
        task_id, plan_id = await _task_with_plan(db, company.id)
        await confirm_plan(
            db, company.id, task_id, company.general_manager_employee_id
        )
        task = await get_company_task(db, company.id, task_id)
        assert task["status"] == "approved"
