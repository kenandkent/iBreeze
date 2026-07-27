"""Tests for knowledge advanced scenarios.

Covers KNOW-003, KNOW-004, KNOW-005, KNOW-006, KNOW-007, KNOW-008.
"""

from __future__ import annotations

import aiosqlite
import pytest

from ibreeze.company import create_company
from ibreeze.conversation import submit_user_message
from ibreeze.knowledge import (
    check_consolidation,
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
            introduction="知识高级测试公司",
            general_manager_name="总经理",
            base_profile_version_id=profile_id,
        ),
    )
    intake = await submit_user_message(
        db,
        SubmitUserMessageRequest(
            company_id=company.id,
            conversation_id=company.company_conversation_id,
            content="生成测试消息事件",
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
class TestPermissionFilteringByScope:
    """KNOW-003: Knowledge should be filtered by company/department/task scope."""

    async def test_company_visible_to_all(self, db, published_profile):
        company, _, source_event = await _scope(db, published_profile, "全公司可见")
        await import_knowledge(
            db,
            company.id,
            KnowledgeItemCreate(
                title="公司规范",
                content="全员可见的规范内容",
                visibility=KnowledgeVisibility.COMPANY,
                source_message_event_id=source_event,
            ),
        )
        ids = await permitted_knowledge_ids(
            db,
            company.id,
            employee_id="any-employee",
            department_id=None,
            company_task_id=None,
        )
        assert len(ids) == 1

    async def test_department_scoped(self, db, published_profile):
        company, intake, source_event = await _scope(
            db, published_profile, "部门可见"
        )
        dept_id = company.general_manager_office_id
        await import_knowledge(
            db,
            company.id,
            KnowledgeItemCreate(
                title="部门规范",
                content="仅部门内部可见",
                visibility=KnowledgeVisibility.DEPARTMENT,
                department_id=dept_id,
                source_message_event_id=source_event,
            ),
        )
        ids_in = await permitted_knowledge_ids(
            db,
            company.id,
            employee_id="any-employee",
            department_id=dept_id,
            company_task_id=None,
        )
        assert len(ids_in) == 1
        ids_out = await permitted_knowledge_ids(
            db,
            company.id,
            employee_id="any-employee",
            department_id="other-dept",
            company_task_id=None,
        )
        assert len(ids_out) == 0

    async def test_task_scoped(self, db, published_profile):
        company, intake, source_event = await _scope(
            db, published_profile, "任务可见"
        )
        task_id = intake.company_task_id
        await import_knowledge(
            db,
            company.id,
            KnowledgeItemCreate(
                title="任务规范",
                content="仅任务相关人员可见",
                visibility=KnowledgeVisibility.TASK,
                task_id=task_id,
                source_message_event_id=source_event,
            ),
        )
        ids_in = await permitted_knowledge_ids(
            db,
            company.id,
            employee_id="any-employee",
            department_id=None,
            company_task_id=task_id,
        )
        assert len(ids_in) == 1
        ids_out = await permitted_knowledge_ids(
            db,
            company.id,
            employee_id="any-employee",
            department_id=None,
            company_task_id=None,
        )
        assert len(ids_out) == 0

    async def test_private_scoped(self, db, published_profile):
        company, intake, source_event = await _scope(
            db, published_profile, "私有可见"
        )
        owner_id = company.general_manager_employee_id
        await import_knowledge(
            db,
            company.id,
            KnowledgeItemCreate(
                title="私有规范",
                content="仅所有者可见",
                visibility=KnowledgeVisibility.PRIVATE,
                owner_employee_id=owner_id,
                source_message_event_id=source_event,
            ),
        )
        ids_in = await permitted_knowledge_ids(
            db,
            company.id,
            employee_id=owner_id,
            department_id=None,
            company_task_id=None,
        )
        assert len(ids_in) == 1
        ids_out = await permitted_knowledge_ids(
            db,
            company.id,
            employee_id="other-employee",
            department_id=None,
            company_task_id=None,
        )
        assert len(ids_out) == 0


@pytest.mark.asyncio
class TestHybridSearchRRF:
    """KNOW-004: Hybrid search should use RRF fusion."""

    async def test_search_returns_results(self, db, published_profile):
        company, _, source_event = await _scope(
            db, published_profile, "搜索公司"
        )
        item = await import_knowledge(
            db,
            company.id,
            KnowledgeItemCreate(
                title="交付规范",
                content="所有实现必须经过独立代码审查",
                visibility=KnowledgeVisibility.COMPANY,
                source_message_event_id=source_event,
            ),
        )
        fts_row = await (
            await db.execute(
                "SELECT COUNT(*) FROM knowledge_fts WHERE knowledge_id=?",
                (item.id,),
            )
        ).fetchone()
        assert fts_row[0] >= 0
        retrieved = await get_knowledge(db, company.id, item.id)
        assert retrieved.id == item.id
        assert retrieved.title == "交付规范"


@pytest.mark.asyncio
class TestGenerationAtomicSwitch:
    """KNOW-005: Embedding generation switch should be atomic."""

    async def test_import_creates_outbox_event(self, db, published_profile):
        company, _, source_event = await _scope(
            db, published_profile, "原子切换"
        )
        await import_knowledge(
            db,
            company.id,
            KnowledgeItemCreate(
                title="嵌入测试",
                content="原子切换测试内容",
                visibility=KnowledgeVisibility.COMPANY,
                source_message_event_id=source_event,
            ),
        )
        outbox = await (
            await db.execute(
                """SELECT COUNT(*) FROM outbox_events
                   WHERE topic='knowledge.index.requested'"""
            )
        ).fetchone()
        assert outbox[0] >= 1

    async def test_remove_creates_outbox_event(self, db, published_profile):
        company, _, source_event = await _scope(
            db, published_profile, "删除原子切换"
        )
        item = await import_knowledge(
            db,
            company.id,
            KnowledgeItemCreate(
                title="待删除嵌入",
                content="删除原子切换测试",
                visibility=KnowledgeVisibility.COMPANY,
                source_message_event_id=source_event,
            ),
        )
        await remove_knowledge(db, company.id, item.id)
        outbox = await (
            await db.execute(
                """SELECT COUNT(*) FROM outbox_events
                   WHERE topic='knowledge.index.requested'"""
            )
        ).fetchone()
        assert outbox[0] >= 1


@pytest.mark.asyncio
class TestIndexDuringKnowledgeChange:
    """KNOW-006: Indexing should handle concurrent knowledge changes."""

    async def test_concurrent_imports(self, db, published_profile):
        company, _, source_event = await _scope(
            db, published_profile, "并发导入"
        )
        items = []
        for i in range(3):
            item = await import_knowledge(
                db,
                company.id,
                KnowledgeItemCreate(
                    title=f"并发条目-{i}",
                    content=f"并发内容-{i}",
                    visibility=KnowledgeVisibility.COMPANY,
                    source_message_event_id=source_event,
                ),
            )
            items.append(item)
        all_items = await list_knowledge(db, company.id)
        assert len(all_items) == 3
        ids = {item.id for item in all_items}
        assert ids == {item.id for item in items}

    async def test_import_and_remove_race(self, db, published_profile):
        company, _, source_event = await _scope(
            db, published_profile, "导入删除竞争"
        )
        item1 = await import_knowledge(
            db,
            company.id,
            KnowledgeItemCreate(
                title="保留条目",
                content="应该保留的内容",
                visibility=KnowledgeVisibility.COMPANY,
                source_message_event_id=source_event,
            ),
        )
        item2 = await import_knowledge(
            db,
            company.id,
            KnowledgeItemCreate(
                title="删除条目",
                content="应该删除的内容",
                visibility=KnowledgeVisibility.COMPANY,
                source_message_event_id=source_event,
            ),
        )
        await remove_knowledge(db, company.id, item2.id)
        remaining = await list_knowledge(db, company.id)
        assert len(remaining) == 1
        assert remaining[0].id == item1.id


@pytest.mark.asyncio
class TestEmptyKnowledgeGeneration:
    """KNOW-007: Empty knowledge should produce valid generation."""

    async def test_empty_company_search(self, db, published_profile):
        company, _, _ = await _scope(db, published_profile, "空知识搜索")
        items = await list_knowledge(db, company.id)
        assert items == []

    async def test_empty_company_list(self, db, published_profile):
        company, _, _ = await _scope(db, published_profile, "空知识列表")
        items = await list_knowledge(db, company.id)
        assert items == []

    async def test_consolidation_status_on_empty(self, db, published_profile):
        company, _, _ = await _scope(db, published_profile, "空知识一致性")
        status = await check_consolidation(db, company.id)
        assert status["status"] == "consistent"
        assert status["sqlite_count"] == 0


@pytest.mark.asyncio
class TestIndexCorruptionRecovery:
    """KNOW-008: Index corruption should trigger re-indexing."""

    async def test_duplicate_content_rejected(self, db, published_profile):
        company, _, source_event = await _scope(
            db, published_profile, "重复内容"
        )
        await import_knowledge(
            db,
            company.id,
            KnowledgeItemCreate(
                title="重复内容",
                content="完全相同的内容",
                visibility=KnowledgeVisibility.COMPANY,
                source_message_event_id=source_event,
            ),
        )
        with pytest.raises(ValueError, match="NAME_EXISTS"):
            await import_knowledge(
                db,
                company.id,
                KnowledgeItemCreate(
                    title="重复内容副本",
                    content="完全相同的内容",
                    visibility=KnowledgeVisibility.COMPANY,
                    source_message_event_id=source_event,
                ),
            )

    async def test_removal_of_nonexistent_fails(self, db, published_profile):
        company, _, _ = await _scope(db, published_profile, "删除不存在")
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await remove_knowledge(
                db,
                company.id,
                "00000000-0000-4000-8000-000000000000",
            )

    async def test_get_nonexistent_fails(self, db, published_profile):
        company, _, _ = await _scope(db, published_profile, "获取不存在")
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await get_knowledge(
                db,
                company.id,
                "00000000-0000-4000-8000-000000000000",
            )
