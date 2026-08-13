"""Tests for task/service.py gap coverage: get_task_graph, get_task_evidence,
check_department_resources, replace_employee, get_department_task_report."""

from __future__ import annotations

import uuid

import aiosqlite
import pytest

from ibreeze.task.service import (
    cancel_task,
    check_department_resources,
    confirm_plan,
    get_department_task_report,
    get_task_evidence,
    get_task_graph,
    pause_task,
    reject_plan,
    replace_employee,
    request_plan_revision,
    resume_task,
    submit_plan_for_review,
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


async def _set_status(db: aiosqlite.Connection, task_id: str, status: str) -> None:
    await db.execute("UPDATE company_tasks SET status=? WHERE id=?", (status, task_id))
    await db.commit()


async def _insert_plan(db: aiosqlite.Connection, company_id: str, task_id: str, status: str) -> str:
    plan_id = str(uuid.uuid4())
    sha = "a" * 64
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """INSERT INTO company_plan_versions
               (id, company_task_id, company_id, version_number, canonical_json,
                content_sha256, generated_by_run_id, status, created_at)
               VALUES (?, ?, ?, 1, '{}', ?, 'run-1', ?, '2026-01-01T00:00:00Z')""",
            (plan_id, task_id, company_id, sha, status),
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()
    return plan_id


@pytest.mark.asyncio
class TestSubmitPlanForReview:
    async def test_submit_success(self, db):
        company_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        await _ensure_company_and_task(db, company_id, task_id)
        await _set_status(db, task_id, "analyzing")
        plan_id = await _insert_plan(db, company_id, task_id, "draft")
        result = await submit_plan_for_review(db, company_id, task_id, "e1")
        assert result["status"] == "awaiting_user_confirmation"
        assert result["plan_version_id"] == plan_id

    async def test_submit_not_found(self, db):
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await submit_plan_for_review(db, "co", "nonexistent", "e1")

    async def test_submit_wrong_state(self, db):
        company_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        await _ensure_company_and_task(db, company_id, task_id)
        await _set_status(db, task_id, "executing")
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await submit_plan_for_review(db, company_id, task_id, "e1")

    async def test_submit_no_draft_plan(self, db):
        company_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        await _ensure_company_and_task(db, company_id, task_id)
        await _set_status(db, task_id, "draft")
        with pytest.raises(ValueError, match="NO_DRAFT_PLAN"):
            await submit_plan_for_review(db, company_id, task_id, "e1")


@pytest.mark.asyncio
class TestConfirmPlanGaps:
    async def test_confirm_success(self, db):
        company_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        await _ensure_company_and_task(db, company_id, task_id)
        await _set_status(db, task_id, "awaiting_user_confirmation")
        await _insert_plan(db, company_id, task_id, "awaiting_user_confirmation")
        result = await confirm_plan(db, company_id, task_id, "e1")
        assert result["status"] == "approved"

    async def test_confirm_no_awaiting_plan(self, db):
        company_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        await _ensure_company_and_task(db, company_id, task_id)
        await _set_status(db, task_id, "awaiting_user_confirmation")
        with pytest.raises(ValueError, match="NO_AWAITING_PLAN"):
            await confirm_plan(db, company_id, task_id, "e1")


@pytest.mark.asyncio
class TestRequestRevisionGaps:
    async def test_supersedes_existing_plan(self, db):
        company_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        await _ensure_company_and_task(db, company_id, task_id)
        await _set_status(db, task_id, "awaiting_user_confirmation")
        await _insert_plan(db, company_id, task_id, "awaiting_user_confirmation")
        result = await request_plan_revision(db, company_id, task_id, "e1", reason="revise")
        assert result["status"] == "revision_requested"

    async def test_revision_not_found(self, db):
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await request_plan_revision(db, "co", "nonexistent", "e1", reason="x")

    async def test_revision_wrong_state(self, db):
        company_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        await _ensure_company_and_task(db, company_id, task_id)
        await _set_status(db, task_id, "draft")
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await request_plan_revision(db, company_id, task_id, "e1", reason="x")


@pytest.mark.asyncio
class TestRejectPlanGaps:
    async def test_reject_with_plan(self, db):
        company_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        await _ensure_company_and_task(db, company_id, task_id)
        await _set_status(db, task_id, "awaiting_user_confirmation")
        await _insert_plan(db, company_id, task_id, "awaiting_user_confirmation")
        result = await reject_plan(db, company_id, task_id, "e1", reason="no")
        assert result["status"] == "rejected"

    async def test_reject_not_found(self, db):
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await reject_plan(db, "co", "nonexistent", "e1", reason="x")


@pytest.mark.asyncio
class TestPauseResumeGaps:
    async def test_pause_not_found(self, db):
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await pause_task(db, "co", "nonexistent", "e1")

    async def test_resume_success(self, db):
        company_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        await _ensure_company_and_task(db, company_id, task_id)
        await _set_status(db, task_id, "executing")
        paused = await pause_task(db, company_id, task_id, "e1")
        assert paused["resume_state"] == "executing"
        result = await resume_task(db, company_id, task_id, "e1")
        assert result["status"] == "executing"

    async def test_resume_not_found(self, db):
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await resume_task(db, "co", "nonexistent", "e1")


@pytest.mark.asyncio
class TestCancelTaskGaps:
    async def test_cancel_success(self, db):
        company_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        await _ensure_company_and_task(db, company_id, task_id)
        await _set_status(db, task_id, "draft")
        result = await cancel_task(db, company_id, task_id, "e1", reason="x")
        assert result["status"] == "cancelling"

    async def test_cancel_not_found(self, db):
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await cancel_task(db, "co", "nonexistent", "e1", reason="x")


@pytest.mark.asyncio
class TestReplaceEmployeeSuccess:
    async def test_replace_success(self, db):
        company_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        dept_task_id = str(uuid.uuid4())
        dept_id = str(uuid.uuid4())
        emp_old = str(uuid.uuid4())
        emp_new = str(uuid.uuid4())
        await _ensure_company_and_task(db, company_id, task_id)
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                """INSERT INTO employees
                   (id, company_id, department_id, display_name, normalized_display_name,
                    base_profile_version_id, workflow_role, status, created_at, updated_at, version)
                   VALUES (?, ?, ?, 'Old', 'old', 'p1', 'member', 'active', ?, ?, 1),
                          (?, ?, ?, 'New', 'new', 'p1', 'member', 'active', ?, ?, 1)""",
                (
                    emp_old,
                    company_id,
                    dept_id,
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:00:00Z",
                    emp_new,
                    company_id,
                    dept_id,
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:00:00Z",
                ),
            )
            await db.execute(
                """INSERT INTO department_tasks
                   (id, company_id, company_task_id, department_id, stage_key, objective,
                    deliverables_json, acceptance_criteria_json, status, created_at, updated_at, version)
                   VALUES (?, ?, ?, ?, 'stage-1', 'Do things', '[]', '[]', 'draft', ?, ?, 1)""",
                (dept_task_id, company_id, task_id, dept_id, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
            )
            await db.execute(
                """INSERT INTO employee_tasks
                   (id, company_id, department_task_id, employee_id, task_kind, objective,
                    acceptance_criteria_json, status, created_at, updated_at, version)
                   VALUES (?, ?, ?, ?, 'standard', 'Obj', '[]', 'assigned', ?, ?, 1)""",
                (str(uuid.uuid4()), company_id, dept_task_id, emp_old, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
            )
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        await db.commit()
        result = await replace_employee(
            db,
            company_id,
            dept_task_id,
            old_employee_id=emp_old,
            new_employee_id=emp_new,
        )
        assert result["new_employee_id"] == emp_new
        assert result["old_employee_id"] == emp_old
        assert result["new_task_id"]


class _Cursor:
    def __init__(self, row, rowcount: int) -> None:
        self.rowcount = rowcount
        self._row = row

    async def fetchone(self):
        return self._row

    async def fetchall(self):
        return []


class _Db:
    """Mock db: same SELECT row everywhere; rowcount keyed by sql substring."""

    def __init__(self, row, rowcounts=None) -> None:
        self._row = row
        self._rowcounts = rowcounts or {}

    async def execute(self, sql, args=()):
        rc = 0
        for sub, val in self._rowcounts.items():
            if sub in sql:
                rc = val
                break
        return _Cursor(self._row, rc)


@pytest.mark.asyncio
class TestOptimisticLockConflicts:
    async def test_submit_first_lock_conflict(self):
        db = _Db({"id": "p1", "status": "analyzing"}, {"company_plan_versions": 0})
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await submit_plan_for_review(db, "c1", "t1", "e1")

    async def test_submit_second_lock_conflict(self):
        db = _Db({"id": "p1", "status": "analyzing"}, {"company_plan_versions": 1, "company_tasks": 0})
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await submit_plan_for_review(db, "c1", "t1", "e1")

    async def test_confirm_lock_conflict(self):
        db = _Db({"id": "p1", "status": "awaiting_user_confirmation"}, {"company_tasks": 0})
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await confirm_plan(db, "c1", "t1", "e1")

    async def test_request_revision_lock_conflict(self):
        db = _Db({"id": "p1", "status": "awaiting_user_confirmation"}, {"company_tasks": 0})
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await request_plan_revision(db, "c1", "t1", "e1", reason="x")

    async def test_reject_lock_conflict(self):
        db = _Db({"id": "p1", "status": "awaiting_user_confirmation"}, {"company_tasks": 0})
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await reject_plan(db, "c1", "t1", "e1", reason="x")

    async def test_pause_lock_conflict(self):
        db = _Db({"status": "executing"}, {"company_tasks": 0})
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await pause_task(db, "c1", "t1", "e1")

    async def test_resume_lock_conflict(self):
        db = _Db({"status": "paused", "resume_state": "executing"}, {"company_tasks": 0})
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await resume_task(db, "c1", "t1", "e1")

    async def test_cancel_lock_conflict(self):
        db = _Db({"status": "draft"}, {"company_tasks": 0})
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await cancel_task(db, "c1", "t1", "e1", reason="x")


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
                db,
                str(uuid.uuid4()),
                "nonexistent",
                old_employee_id="old",
                new_employee_id="new",
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
