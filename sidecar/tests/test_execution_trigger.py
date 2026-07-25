"""Tests for dispatcher and run executor — execution trigger chain."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import aiosqlite
import pytest

from ibreeze.company import create_company
from ibreeze.conversation import get_company_conversation, submit_user_message
from ibreeze.schemas import CompanyCreate, SubmitUserMessageRequest
from ibreeze.task.service import confirm_plan
from ibreeze.orchestration.dispatcher import dispatch_company_task
from ibreeze.runtime.run_executor import execute_single_run


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def _company(db: aiosqlite.Connection, profile_id: str, name: str):
    return await create_company(
        db,
        CompanyCreate(
            name=name,
            introduction="测试公司介绍",
            general_manager_name="总经理",
            base_profile_version_id=profile_id,
        ),
    )


async def _task_with_status(
    db: aiosqlite.Connection, company_id: str, status: str,
) -> str:
    conversation = await get_company_conversation(db, company_id)
    result = await submit_user_message(
        db,
        SubmitUserMessageRequest(
            company_id=company_id,
            conversation_id=conversation.id,
            content="创建任务用于执行触发测试",
        ),
    )
    task_id = result.company_task_id
    await db.execute(
        "UPDATE company_tasks SET status=? WHERE id=?",
        (status, task_id),
    )
    await db.commit()
    return task_id


class TestDispatcher:
    """Tests for dispatch_company_task."""

    @pytest.mark.asyncio
    async def test_dispatch_creates_dept_and_emp_tasks(self, db, published_profile):
        company = await _company(db, published_profile, "调度公司")

        # Get employee_id
        cursor = await db.execute(
            "SELECT id FROM employees WHERE company_id=?",
            (company.id,),
        )
        emp_row = await cursor.fetchone()
        emp_id = emp_row["id"]

        # Get department_id (GM office)
        dept_id = company.general_manager_office_id

        # Create a task in 'dispatching' status
        task_id = await _task_with_status(db, company.id, "dispatching")

        # Create an approved plan
        plan_id = _id()
        plan = {
            "department_tasks": [
                {
                    "local_ref": "dt-1",
                    "department_id": dept_id,
                    "objective": "构建功能X",
                    "acceptance_criteria": ["通过测试"],
                    "dependency_refs": [],
                    "deliverables": [
                        {
                            "artifact_type": "code",
                            "contributor_employee_ids": [emp_id],
                        }
                    ],
                }
            ],
        }
        now = _now()
        await db.execute(
            """INSERT INTO company_plan_versions
               (id, company_task_id, company_id, version_number, canonical_json,
                content_sha256, generated_by_run_id, status, created_at)
               VALUES (?,?,?,?,?,?,?,'approved',?)""",
            (plan_id, task_id, company.id, 1,
             json.dumps(plan), "a" * 64, _id(), now),
        )
        await db.commit()

        result = await dispatch_company_task(db, company.id, task_id)

        assert result["status"] == "executing"
        assert result["department_tasks_created"] >= 1
        assert result["employee_tasks_created"] >= 1

        # Verify department_task was created
        cursor = await db.execute(
            "SELECT id FROM department_tasks WHERE company_task_id=? AND company_id=?",
            (task_id, company.id),
        )
        rows = await cursor.fetchall()
        assert len(rows) >= 1

        # Verify agent_run was enqueued
        cursor = await db.execute(
            "SELECT id FROM agent_runs WHERE company_task_id=? AND company_id=?",
            (task_id, company.id),
        )
        rows = await cursor.fetchall()
        assert len(rows) >= 1

    @pytest.mark.asyncio
    async def test_dispatch_rejects_non_dispatching_status(self, db, published_profile):
        company = await _company(db, published_profile, "非调度公司")
        task_id = await _task_with_status(db, company.id, "executing")

        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await dispatch_company_task(db, company.id, task_id)

    @pytest.mark.asyncio
    async def test_dispatch_rejects_missing_task(self, db, published_profile):
        company = await _company(db, published_profile, "缺失公司")
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await dispatch_company_task(db, company.id, "nonexistent")


class TestRunExecutor:
    """Tests for execute_single_run."""

    @pytest.mark.asyncio
    async def test_execute_run_not_found(self, db):
        result = await execute_single_run(db, "nonexistent", "nonexistent_company")
        assert result["error"] == "RUN_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_execute_run_already_terminal(self, db, published_profile):
        company = await _company(db, published_profile, "终态公司")

        # Get employee_id
        cursor = await db.execute(
            "SELECT id FROM employees WHERE company_id=?",
            (company.id,),
        )
        emp_row = await cursor.fetchone()

        run_id = _id()
        work_id = _id()
        now = _now()
        await db.execute(
            """INSERT INTO agent_runs
               (id, company_id, company_task_id, department_task_id,
                employee_task_id, work_item_id, employee_id,
                conversation_id, availability_snapshot_id, execution_snapshot_id,
                run_purpose, adapter_type, run_spec_json, run_spec_sha256,
                status, attempt, created_at, updated_at, version)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,1)""",
            (run_id, company.id, _id(), _id(),
             work_id, work_id, emp_row["id"], "",
             "snap_" + _id(), "snap_" + _id(), "task_execution", "codex_cli",
             json.dumps({"prompt": "test"}), "a" * 64, "succeeded", now, now),
        )
        await db.commit()

        result = await execute_single_run(db, run_id, company.id)
        assert result["error"] == "RUN_ALREADY_TERMINAL"
