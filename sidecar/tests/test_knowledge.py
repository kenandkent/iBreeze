"""Knowledge source, transaction and permission tests."""

from __future__ import annotations

import json

import aiosqlite
import pytest

from ibreeze.company import create_company
from ibreeze.conversation import submit_user_message
from ibreeze.knowledge import (
    get_knowledge,
    import_knowledge,
    list_knowledge,
    permitted_knowledge_ids,
    remove_knowledge,
)
from ibreeze.schemas import (
    CompanyCreate,
    KnowledgeItemCreate,
    KnowledgeVisibility,
    SubmitUserMessageRequest,
)


async def _scope(db: aiosqlite.Connection, profile_id: str, name: str):
    company = await create_company(
        db,
        CompanyCreate(
            name=name,
            introduction="知识权限测试公司",
            general_manager_name="总经理",
            base_profile_version_id=profile_id,
        ),
    )
    intake = await submit_user_message(
        db,
        SubmitUserMessageRequest(
            company_id=company.id,
            conversation_id=company.company_conversation_id,
            content="生成稳定消息事件",
        ),
    )
    message = await (
        await db.execute(
            "SELECT source_event_id FROM conversation_messages WHERE id=?",
            (intake.message_id,),
        )
    ).fetchone()
    return company, intake, message[0]


@pytest.mark.asyncio
async def test_import_is_atomic_and_event_payload_excludes_content(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company, _, source_event = await _scope(
        db,
        published_profile,
        "知识导入公司",
    )
    imported = await import_knowledge(
        db,
        company.id,
        KnowledgeItemCreate(
            title="交付规范",
            content="所有实现必须经过独立 Review。",
            visibility=KnowledgeVisibility.COMPANY,
            source_message_event_id=source_event,
        ),
    )
    assert (await get_knowledge(db, company.id, imported.id)).content_sha256
    assert [item.id for item in await list_knowledge(db, company.id)] == [
        imported.id
    ]
    event = await (
        await db.execute(
            """SELECT payload_json FROM domain_events
               WHERE aggregate_id=? AND event_type='knowledge.imported'""",
            (imported.id,),
        )
    ).fetchone()
    payload = json.loads(event[0])
    assert "content" not in payload
    assert payload["content_sha256"] == imported.content_sha256
    assert (
        await (
            await db.execute(
                """SELECT COUNT(*) FROM outbox_events
                   WHERE topic='knowledge.index.requested'""",
            )
        ).fetchone()
    )[0] == 1


@pytest.mark.asyncio
async def test_permission_candidates_are_filtered_before_retrieval(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company, intake, source_event = await _scope(
        db,
        published_profile,
        "知识隔离公司",
    )
    employee_id = company.general_manager_employee_id
    department_id = company.general_manager_office_id
    items = []
    for visibility, scope in (
        (KnowledgeVisibility.COMPANY, {}),
        (
            KnowledgeVisibility.DEPARTMENT,
            {"department_id": department_id},
        ),
        (
            KnowledgeVisibility.TASK,
            {"task_id": intake.company_task_id},
        ),
        (
            KnowledgeVisibility.PRIVATE,
            {"owner_employee_id": employee_id},
        ),
    ):
        items.append(
            await import_knowledge(
                db,
                company.id,
                KnowledgeItemCreate(
                    title=f"{visibility.value} 规范",
                    content=f"{visibility.value} 可见内容",
                    visibility=visibility,
                    source_message_event_id=source_event,
                    **scope,
                ),
            )
        )
    allowed = await permitted_knowledge_ids(
        db,
        company.id,
        employee_id=employee_id,
        department_id=department_id,
        company_task_id=intake.company_task_id,
    )
    assert set(allowed) == {item.id for item in items}
    unrelated = await permitted_knowledge_ids(
        db,
        company.id,
        employee_id="00000000-0000-4000-8000-000000000000",
        department_id=None,
        company_task_id=None,
    )
    assert unrelated == [items[0].id]


@pytest.mark.asyncio
async def test_remove_records_fact_before_deleting_item(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company, _, source_event = await _scope(
        db,
        published_profile,
        "知识删除公司",
    )
    item = await import_knowledge(
        db,
        company.id,
        KnowledgeItemCreate(
            title="临时规范",
            content="待删除正文",
            visibility=KnowledgeVisibility.COMPANY,
            source_message_event_id=source_event,
        ),
    )
    result = await remove_knowledge(db, company.id, item.id)
    assert result == {"id": item.id, "removed": True}
    with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
        await get_knowledge(db, company.id, item.id)
    removed = await (
        await db.execute(
            """SELECT aggregate_version,payload_json FROM domain_events
               WHERE aggregate_id=? AND event_type='knowledge.removed'""",
            (item.id,),
        )
    ).fetchone()
    assert removed[0] == 2
    assert "待删除正文" not in removed[1]


@pytest.mark.asyncio
async def test_cross_company_source_is_rejected_by_composite_fk(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    first, _, source_event = await _scope(db, published_profile, "来源公司")
    second, _, _ = await _scope(db, published_profile, "目标公司")
    with pytest.raises(aiosqlite.IntegrityError):
        await import_knowledge(
            db,
            second.id,
            KnowledgeItemCreate(
                title="越权来源",
                content="不能导入",
                visibility=KnowledgeVisibility.COMPANY,
                source_message_event_id=source_event,
            ),
        )
    assert await list_knowledge(db, second.id) == []
    assert first.id != second.id
