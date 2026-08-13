"""Coverage-focused tests for conversation commands (error and pagination branches)."""

from __future__ import annotations

import uuid

import aiosqlite
import pytest

from ibreeze.company import create_company
from ibreeze.conversation import (
    archive_conversation,
    create_conversation,
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
            introduction="覆盖会话错误与分页分支",
            general_manager_name="总经理",
            base_profile_version_id=profile_id,
        ),
    )


@pytest.mark.asyncio
async def test_get_company_conversation_not_found(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
        await get_company_conversation(db, str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_get_department_conversation_not_found(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "部门会话覆盖公司")
    with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
        await get_department_conversation(db, company.id, str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_list_messages_pagination_after(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "消息分页公司")
    conversation = await get_company_conversation(db, company.id)
    first = await submit_user_message(
        db,
        SubmitUserMessageRequest(
            company_id=company.id,
            conversation_id=conversation.id,
            content="第一条消息",
        ),
    )
    await submit_user_message(
        db,
        SubmitUserMessageRequest(
            company_id=company.id,
            conversation_id=conversation.id,
            content="第二条消息",
        ),
    )
    all_messages = await list_messages(db, company.id, conversation.id)
    assert [m.id for m in all_messages] == [first.message_id, all_messages[1].id]
    anchor = all_messages[0]
    row = await (
        await db.execute(
            "SELECT created_at FROM conversation_messages WHERE id=?",
            (anchor.id,),
        )
    ).fetchone()
    after = await list_messages(
        db,
        company.id,
        conversation.id,
        after=(row[0], anchor.id),
    )
    assert anchor.id not in [m.id for m in after]


@pytest.mark.asyncio
async def test_create_conversation_rejects_missing_and_archived_company(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
        await create_conversation(db, str(uuid.uuid4()), "无效公司")
    company = await _company(db, published_profile, "已归档会话公司")
    await db.execute("UPDATE companies SET status='archived' WHERE id=?", (company.id,))
    await db.commit()
    with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
        await create_conversation(db, company.id, "已归档公司会话")


@pytest.mark.asyncio
async def test_archive_conversation(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "归档会话公司")
    conversation = await get_company_conversation(db, company.id)
    result = await archive_conversation(db, company.id, conversation.id)
    assert set(result.keys()) == {"archived_at"}
    row = await (
        await db.execute(
            "SELECT status FROM conversations WHERE id=?",
            (conversation.id,),
        )
    ).fetchone()
    assert row[0] == "archived"
    with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
        await archive_conversation(db, company.id, str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_submit_rejects_target_and_supersedes_together(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "校验冲突公司")
    conversation = await get_company_conversation(db, company.id)
    with pytest.raises(ValueError, match="VALIDATION_FAILED"):
        await submit_user_message(
            db,
            SubmitUserMessageRequest(
                company_id=company.id,
                conversation_id=conversation.id,
                content="同时指定目标与接替",
                target_task_id=str(uuid.uuid4()),
                supersedes_task_id=str(uuid.uuid4()),
            ),
        )


@pytest.mark.asyncio
async def test_submit_rejects_archived_company(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "提交归档公司")
    conversation = await get_company_conversation(db, company.id)
    await db.execute("UPDATE companies SET status='archived' WHERE id=?", (company.id,))
    await db.commit()
    with pytest.raises(ValueError, match="COMPANY_ARCHIVED"):
        await submit_user_message(
            db,
            SubmitUserMessageRequest(
                company_id=company.id,
                conversation_id=conversation.id,
                content="归档后消息",
            ),
        )


@pytest.mark.asyncio
async def test_submit_superseding_task_mode(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "接替任务公司")
    conversation = await get_company_conversation(db, company.id)
    first = await submit_user_message(
        db,
        SubmitUserMessageRequest(
            company_id=company.id,
            conversation_id=conversation.id,
            content="被接替的旧需求",
        ),
    )
    await db.execute("UPDATE company_tasks SET status='cancelled' WHERE id=?", (first.company_task_id,))
    await db.commit()
    superseding = await submit_user_message(
        db,
        SubmitUserMessageRequest(
            company_id=company.id,
            conversation_id=conversation.id,
            content="接替后的新需求",
            supersedes_task_id=first.company_task_id,
        ),
    )
    assert superseding.intake_mode == "superseding_task"
    assert superseding.task_status == "draft"
    assert superseding.company_task_id != first.company_task_id
    row = await (
        await db.execute(
            "SELECT supersedes_task_id FROM company_tasks WHERE id=?",
            (superseding.company_task_id,),
        )
    ).fetchone()
    assert row[0] == first.company_task_id


@pytest.mark.asyncio
async def test_submit_rejects_superseding_non_cancelled_task(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "接替校验公司")
    conversation = await get_company_conversation(db, company.id)
    first = await submit_user_message(
        db,
        SubmitUserMessageRequest(
            company_id=company.id,
            conversation_id=conversation.id,
            content="仍为草稿的任务",
        ),
    )
    with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
        await submit_user_message(
            db,
            SubmitUserMessageRequest(
                company_id=company.id,
                conversation_id=conversation.id,
                content="尝试接替草稿",
                supersedes_task_id=first.company_task_id,
            ),
        )
    with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
        await submit_user_message(
            db,
            SubmitUserMessageRequest(
                company_id=company.id,
                conversation_id=conversation.id,
                content="尝试接替不存在的任务",
                supersedes_task_id=str(uuid.uuid4()),
            ),
        )
