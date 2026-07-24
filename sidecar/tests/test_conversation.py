"""Conversation intake transaction and scope tests."""

from __future__ import annotations

import aiosqlite
import pytest

from ibreeze.company import create_company
from ibreeze.conversation import (
    get_company_conversation,
    get_department_conversation,
    list_messages,
    submit_user_message,
)
from ibreeze.schemas import CompanyCreate, SubmitUserMessageRequest


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


@pytest.mark.asyncio
async def test_company_message_creates_task_event_projection_and_outbox(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "会话公司")
    conversation = await get_company_conversation(db, company.id)
    result = await submit_user_message(
        db,
        SubmitUserMessageRequest(
            company_id=company.id,
            conversation_id=conversation.id,
            content="实现一个可交付的登录功能",
        ),
    )
    assert result.task_status == "draft"
    assert result.intake_mode == "new_task"
    assert result.analysis_queued is True
    assert result.model_dump().keys() == {
        "message_id",
        "company_task_id",
        "task_status",
        "intake_mode",
        "analysis_queued",
    }
    messages = await list_messages(db, company.id, conversation.id)
    assert [message.id for message in messages] == [result.message_id]
    assert messages[0].task_id == result.company_task_id
    assert (
        await (
            await db.execute(
                """SELECT COUNT(*) FROM domain_events
                   WHERE aggregate_id=? AND
                   event_type='conversation.user_message_submitted'""",
                (result.company_task_id,),
            )
        ).fetchone()
    )[0] == 1
    assert (
        await (
            await db.execute(
                """SELECT COUNT(*) FROM outbox_events
                   WHERE topic='company_task.analysis.requested'""",
            )
        ).fetchone()
    )[0] == 1


@pytest.mark.asyncio
async def test_plan_revision_reuses_task_without_new_run_id(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
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
    assert len(await list_messages(db, company.id, conversation.id)) == 2


@pytest.mark.asyncio
async def test_conversation_enforces_company_scope(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    first = await _company(db, published_profile, "第一公司")
    second = await _company(db, published_profile, "第二公司")
    first_conversation = await get_company_conversation(db, first.id)
    with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
        await submit_user_message(
            db,
            SubmitUserMessageRequest(
                company_id=second.id,
                conversation_id=first_conversation.id,
                content="越权消息",
            ),
        )
    office = await get_department_conversation(
        db,
        first.id,
        first.general_manager_office_id,
    )
    with pytest.raises(ValueError, match="COMPANY_SCOPE_VIOLATION"):
        await submit_user_message(
            db,
            SubmitUserMessageRequest(
                company_id=first.id,
                conversation_id=office.id,
                content="部门会话不能作为公司任务入口",
            ),
        )
