"""Tests for task/service.py gap coverage: get_task_graph, get_task_evidence,
check_department_resources, replace_employee, get_department_task_report."""

from __future__ import annotations

import uuid

import aiosqlite
import pytest

from ibreeze.task.service import (
    check_department_resources,
    get_department_task_report,
    get_task_evidence,
    get_task_graph,
    replace_employee,
)


async def _ensure_company_and_task(db: aiosqlite.Connection, company_id: str, task_id: str) -> None:
    now = "2026-01-01T00:00:00Z"
    conv_id = str(uuid.uuid4())
    msg_event = str(uuid.uuid4())
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """INSERT OR IGNORE INTO company_tasks
               (id, company_id, supersedes_task_id, company_conversation_id, user_message_event_id,
                title, status, created_at, updated_at, version)
               VALUES (?, ?, NULL, ?, ?, 'Test', 'draft', ?, ?, 1)""",
            (task_id, company_id, conv_id, msg_event, now, now),
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()


@pytest.mark.asyncio
class TestGetTaskGraph:
    async def test_get_task_graph(self, db):
        company_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        await _ensure_company_and_task(db, company_id, task_id)
        graph = await get_task_graph(db, company_id, task_id)
        assert graph["task_id"] == task_id
        assert graph["department_tasks"] == []
        assert graph["dependencies"] == []

    async def test_get_task_graph_not_found(self, db):
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await get_task_graph(db, "co", "nonexistent")


@pytest.mark.asyncio
class TestGetTaskEvidence:
    async def test_get_task_evidence_empty(self, db):
        company_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        await _ensure_company_and_task(db, company_id, task_id)
        evidence = await get_task_evidence(db, company_id, task_id)
        assert evidence["runs"] == []
        assert evidence["artifacts"] == []


@pytest.mark.asyncio
class TestCheckDepartmentResources:
    async def test_check_resources_not_found(self, db):
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await check_department_resources(db, str(uuid.uuid4()), "nonexistent")

    async def test_check_resources_empty(self, db):
        company_id = str(uuid.uuid4())
        dept_task_id = str(uuid.uuid4())
        dept_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        await _ensure_company_and_task(db, company_id, task_id)
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                """INSERT INTO department_tasks
                   (id, company_id, company_task_id, department_id, stage_key, objective,
                    deliverables_json, acceptance_criteria_json, status, created_at, updated_at, version)
                   VALUES (?, ?, ?, ?, 'stage-1', 'Do things', '[]', '[]', 'draft', ?, ?, 1)""",
                (dept_task_id, company_id, task_id, dept_id, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
            )
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        await db.commit()
        result = await check_department_resources(db, company_id, dept_task_id)
        assert result["has_resources"] is False
        assert result["assigned_employees"] == []


@pytest.mark.asyncio
class TestReplaceEmployee:
    async def test_replace_not_found(self, db):
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await replace_employee(
                db, str(uuid.uuid4()), "nonexistent",
                old_employee_id="old", new_employee_id="new",
            )


@pytest.mark.asyncio
class TestGetDepartmentTaskReport:
    async def test_report_not_found(self, db):
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await get_department_task_report(db, str(uuid.uuid4()), "nonexistent")

    async def test_report_empty(self, db):
        company_id = str(uuid.uuid4())
        dept_task_id = str(uuid.uuid4())
        dept_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        await _ensure_company_and_task(db, company_id, task_id)
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                """INSERT INTO department_tasks
                   (id, company_id, company_task_id, department_id, stage_key, objective,
                    deliverables_json, acceptance_criteria_json, status, created_at, updated_at, version)
                   VALUES (?, ?, ?, ?, 'stage-1', 'Deliver', '[]', '[]', 'draft', ?, ?, 1)""",
                (dept_task_id, company_id, task_id, dept_id, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
            )
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        await db.commit()
        report = await get_department_task_report(db, company_id, dept_task_id)
        assert report["department_task_id"] == dept_task_id
        assert report["employee_tasks"] == []
