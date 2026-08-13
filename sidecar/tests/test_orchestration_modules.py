"""Tests for orchestration modules: report_generator,
plan_generator, role_behavior, availability_checker."""

from __future__ import annotations

import uuid

import aiosqlite
import pytest

from ibreeze.orchestration.availability_checker import (
    AvailabilityReport,
    CheckStatus,
    check_concurrency_slot,
    check_health,
    check_model,
    check_workspace,
    run_availability_checks,
)
from ibreeze.orchestration.plan_generator import generate_company_plan
from ibreeze.orchestration.report_generator import (
    generate_company_review,
    generate_department_report,
    generate_final_report,
)
from ibreeze.orchestration.role_behavior import (
    AgentRole,
    DepartmentHeadBehavior,
    EmployeeBehavior,
    GeneralManagerBehavior,
    create_role_behavior,
)


def _sha256(data: str) -> str:
    import hashlib

    return hashlib.sha256(data.encode()).hexdigest()


async def _setup_orch_env(
    db: aiosqlite.Connection,
    company_id: str,
    version_id: str,
    profile_id: str,
    employee_id: str,
    dept_id: str,
):
    now = "2026-01-01T00:00:00Z"
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        rev_id = str(uuid.uuid4())
        dept_rev_id = str(uuid.uuid4())
        conv_id = str(uuid.uuid4())
        dept_conv_id = str(uuid.uuid4())
        release_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO company_revisions
               (id, company_id, revision_number, name, introduction, content_sha256, created_by_type, created_at)
               VALUES (?, ?, 1, 'Co', 'Intro', ?, 'system', ?)""",
            (rev_id, company_id, _sha256("co"), now),
        )
        await db.execute(
            """INSERT INTO conversations (id, company_id, conversation_type, status, created_at)
               VALUES (?, ?, 'department', 'active', ?)""",
            (dept_conv_id, company_id, now),
        )
        await db.execute(
            """INSERT INTO department_revisions
               (id, department_id, company_id, revision_number, name, function_description, content_sha256, created_at)
               VALUES (?, ?, ?, 1, 'Root', 'Root', ?, ?)""",
            (dept_rev_id, dept_id, company_id, _sha256("root"), now),
        )
        await db.execute(
            """INSERT INTO employees (id, company_id, department_id, display_name, normalized_display_name,
                base_profile_version_id, workflow_role, status, created_at, updated_at, version)
               VALUES (?, ?, ?, 'GM', 'gm', ?, 'general_manager', 'active', ?, ?, 1)""",
            (employee_id, company_id, dept_id, version_id, now, now),
        )
        await db.execute(
            """INSERT INTO departments (id, company_id, department_type, normalized_name, current_revision_id,
                leader_employee_id, department_conversation_id, status, created_at, updated_at, version)
               VALUES (?, ?, 'general_manager_office', 'root', ?, ?, ?, 'active', ?, ?, 1)""",
            (dept_id, company_id, dept_rev_id, employee_id, dept_conv_id, now, now),
        )
        await db.execute(
            """INSERT INTO conversations (id, company_id, conversation_type, status, created_at)
               VALUES (?, ?, 'company', 'active', ?)""",
            (conv_id, company_id, now),
        )
        await db.execute(
            """INSERT INTO companies (id, normalized_name, current_revision_id, general_manager_office_id,
                general_manager_employee_id, company_conversation_id, status, created_at, updated_at, version)
               VALUES (?, 't', ?, ?, ?, ?, 'active', ?, ?, 1)""",
            (company_id, rev_id, dept_id, employee_id, conv_id, now, now),
        )
        await db.execute(
            """INSERT INTO catalog_cache_releases (release_id, release_sequence, manifest_json, manifest_sha256,
                signature, signing_key_id, status, downloaded_at, activated_at)
               VALUES (?, 1, '{}', ?, 'sig', 'key', 'active', ?, ?)""",
            (release_id, _sha256("{}"), now, now),
        )
        await db.execute(
            """INSERT INTO employee_base_profiles (id, company_id, name, normalized_name, description,
                current_version_id, status, created_at, updated_at, version)
               VALUES (?, ?, 'Default', 'default', 'Default', ?, 'active', ?, ?, 1)""",
            (profile_id, company_id, version_id, now, now),
        )
        await db.execute(
            """INSERT INTO employee_base_profile_versions
               (id, profile_id, version_number, name, description, profile_type,
                runtime_binding_json, system_prompt, capability_tags_json,
                tool_policy_json, timeout_seconds, max_retries, workspace_policy,
                catalog_release_id, content_sha256, status, created_at, published_at)
               VALUES (?, ?, 1, 'Default v1', 'Default', 'agent_cli', '{"adapter_type":"codex_cli"}',
                       'Act.', '[]', '{}', 300, 2, 'workspace_rw_external_ro', ?, ?,
                       'published', ?, ?)""",
            (version_id, profile_id, release_id, _sha256("v1"), now, now),
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()


async def _create_task_with_plan(
    db: aiosqlite.Connection,
    company_id: str,
    task_id: str,
    plan_status: str = "draft",
) -> str:
    now = "2026-01-01T00:00:00Z"
    conv_id = str(uuid.uuid4())
    msg_event = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    sha = _sha256("plan")
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """INSERT OR IGNORE INTO company_tasks
               (id, company_id, supersedes_task_id, company_conversation_id, user_message_event_id,
                title, status, created_at, updated_at, version)
               VALUES (?, ?, NULL, ?, ?, 'Test Task', 'draft', ?, ?, 1)""",
            (task_id, company_id, conv_id, msg_event, now, now),
        )
        # Insert agent_run for FK on generated_by_run_id
        await db.execute(
            """INSERT INTO agent_runs
               (id, company_id, company_task_id, work_item_id, employee_id,
                conversation_id, availability_snapshot_id, execution_snapshot_id,
                run_purpose, adapter_type, run_spec_json, run_spec_sha256,
                status, attempt, created_at, updated_at, version)
               VALUES (?, ?, ?, ?, ?, ?, 'avail', 'exec', 'company_plan', 'codex_cli', '{}', ?,
                       'queued', 1, ?, ?, 1)""",
            (run_id, company_id, task_id, task_id, str(uuid.uuid4()), str(uuid.uuid4()), sha, now, now),
        )
        await db.execute(
            """INSERT INTO company_plan_versions
               (id, company_task_id, company_id, version_number, canonical_json,
                content_sha256, generated_by_run_id, status, created_at)
               VALUES (?, ?, ?, 1, '{}', ?, ?, ?, ?)""",
            (plan_id, task_id, company_id, sha, run_id, plan_status, now),
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()
    return plan_id


@pytest.fixture
async def orch_env(db: aiosqlite.Connection):
    company_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    profile_id = str(uuid.uuid4())
    employee_id = str(uuid.uuid4())
    dept_id = str(uuid.uuid4())
    await _setup_orch_env(db, company_id, version_id, profile_id, employee_id, dept_id)
    return {
        "company_id": company_id,
        "version_id": version_id,
        "profile_id": profile_id,
        "employee_id": employee_id,
        "dept_id": dept_id,
    }


# ── report_generator ─────────────────────────────────────────────────
@pytest.mark.asyncio
class TestReportGenerator:
    async def test_generate_department_report(self, db, orch_env):
        report = await generate_department_report(
            db,
            company_id=orch_env["company_id"],
            department_id=orch_env["dept_id"],
            task_id=str(uuid.uuid4()),
        )
        assert report["report_type"] == "department"
        assert report["department_id"] == orch_env["dept_id"]
        assert report["completed_task_count"] == 0
        assert report["artifact_count"] == 0

    async def test_generate_company_review(self, db, orch_env):
        review = await generate_company_review(
            db,
            company_id=orch_env["company_id"],
            task_id=str(uuid.uuid4()),
        )
        assert review["review_type"] == "company"
        assert review["department_count"] >= 1

    async def test_generate_final_report(self, db, orch_env):
        final = await generate_final_report(
            db,
            company_id=orch_env["company_id"],
            task_id=str(uuid.uuid4()),
        )
        assert final["report_type"] == "final"
        assert len(final["department_reports"]) >= 1
        assert "company_summary" in final


# ── plan_generator ───────────────────────────────────────────────────
@pytest.mark.asyncio
class TestPlanGenerator:
    async def test_generate_company_plan(self, db, orch_env):
        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        now = "2026-01-01T00:00:00Z"
        conv_id = str(uuid.uuid4())
        msg_event = str(uuid.uuid4())
        sha = _sha256("task")
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                """INSERT OR IGNORE INTO company_tasks
                   (id, company_id, supersedes_task_id, company_conversation_id, user_message_event_id,
                    title, status, created_at, updated_at, version)
                   VALUES (?, ?, NULL, ?, ?, 'Test Task', 'draft', ?, ?, 1)""",
                (task_id, orch_env["company_id"], conv_id, msg_event, now, now),
            )
            await db.execute(
                """INSERT INTO agent_runs
                   (id, company_id, company_task_id, work_item_id, employee_id,
                    conversation_id, availability_snapshot_id, execution_snapshot_id,
                    run_purpose, adapter_type, run_spec_json, run_spec_sha256,
                    status, attempt, created_at, updated_at, version)
                   VALUES (?, ?, ?, ?, ?, ?, 'avail', 'exec', 'company_plan', 'codex_cli', '{}', ?,
                           'queued', 1, ?, ?, 1)""",
                (run_id, orch_env["company_id"], task_id, task_id, str(uuid.uuid4()), str(uuid.uuid4()), sha, now, now),
            )
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        await db.commit()
        result = await generate_company_plan(
            db,
            company_id=orch_env["company_id"],
            company_name="TestCo",
            industry="Technology",
            introduction="Build great products",
            general_manager_office="GM Office",
            departments=[
                {
                    "id": orch_env["dept_id"],
                    "name": "Engineering",
                    "responsibilities": [
                        {"title": "Write code", "description": "Write high quality code"},
                    ],
                },
            ],
            company_task_id=task_id,
            generated_by_run_id=run_id,
        )
        assert result["plan_id"]
        assert result["version_id"]
        assert result["status"] == "draft"
        assert len(result["sections"]) >= 2

    async def test_generate_plan_with_no_departments(self, db, orch_env):
        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        now = "2026-01-01T00:00:00Z"
        conv_id = str(uuid.uuid4())
        msg_event = str(uuid.uuid4())
        sha = _sha256("task")
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                """INSERT OR IGNORE INTO company_tasks
                   (id, company_id, supersedes_task_id, company_conversation_id, user_message_event_id,
                    title, status, created_at, updated_at, version)
                   VALUES (?, ?, NULL, ?, ?, 'Test Task', 'draft', ?, ?, 1)""",
                (task_id, orch_env["company_id"], conv_id, msg_event, now, now),
            )
            await db.execute(
                """INSERT INTO agent_runs
                   (id, company_id, company_task_id, work_item_id, employee_id,
                    conversation_id, availability_snapshot_id, execution_snapshot_id,
                    run_purpose, adapter_type, run_spec_json, run_spec_sha256,
                    status, attempt, created_at, updated_at, version)
                   VALUES (?, ?, ?, ?, ?, ?, 'avail', 'exec', 'company_plan', 'codex_cli', '{}', ?,
                           'queued', 1, ?, ?, 1)""",
                (run_id, orch_env["company_id"], task_id, task_id, str(uuid.uuid4()), str(uuid.uuid4()), sha, now, now),
            )
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        await db.commit()
        result = await generate_company_plan(
            db,
            company_id=orch_env["company_id"],
            company_name="SmallCo",
            industry="Consulting",
            introduction="Consult",
            general_manager_office="GM",
            departments=[],
            company_task_id=task_id,
            generated_by_run_id=run_id,
        )
        assert result["plan_id"]


# ── role_behavior ────────────────────────────────────────────────────
class TestRoleBehavior:
    def test_create_general_manager(self):
        behavior = create_role_behavior("general_manager", "emp-1", "co-1")
        assert isinstance(behavior, GeneralManagerBehavior)

    def test_create_department_head(self):
        behavior = create_role_behavior("department_head", "emp-1", "co-1", department_id="dept-1")
        assert isinstance(behavior, DepartmentHeadBehavior)

    def test_create_employee(self):
        behavior = create_role_behavior("employee", "emp-1", "co-1")
        assert isinstance(behavior, EmployeeBehavior)

    @pytest.mark.asyncio
    async def test_general_manager_execute(self):
        behavior = GeneralManagerBehavior("emp-1", "co-1")
        result = await behavior.execute({"task": {"id": "t-1", "title": "Build product"}})
        assert result["action"] == "create_plan"
        assert result["requires_plan_confirmation"] is True

    @pytest.mark.asyncio
    async def test_department_head_execute(self):
        behavior = DepartmentHeadBehavior("emp-1", "co-1", department_id="dept-1")
        result = await behavior.execute({"task": {"id": "t-2", "title": "Organize"}})
        assert result["action"] == "organize_work"
        assert result["department_id"] == "dept-1"

    @pytest.mark.asyncio
    async def test_employee_execute(self):
        behavior = EmployeeBehavior("emp-1", "co-1")
        result = await behavior.execute({"task": {"id": "t-3", "title": "Write code"}})
        assert result["action"] == "execute"

    @pytest.mark.asyncio
    async def test_dispatch_to_departments(self):
        behavior = GeneralManagerBehavior("emp-1", "co-1")
        plan = {
            "sections": [
                {"type": "company_overview"},
                {"type": "department_tasks", "department_id": "d1", "planned_tasks": [{"title": "t1"}]},
                {"type": "department_tasks", "department_id": "d2", "planned_tasks": []},
            ]
        }
        dispatches = await behavior.dispatch_to_departments(plan)
        assert len(dispatches) == 2
        assert dispatches[0]["department_id"] == "d1"

    @pytest.mark.asyncio
    async def test_summarize_results(self):
        behavior = GeneralManagerBehavior("emp-1", "co-1")
        result = await behavior.summarize_results([{"dept": "d1"}, {"dept": "d2"}])
        assert result["department_count"] == 2

    def test_agent_role_enum(self):
        assert AgentRole.GENERAL_MANAGER == "general_manager"
        assert AgentRole.DEPARTMENT_HEAD == "department_head"
        assert AgentRole.EMPLOYEE == "employee"


# ── availability_checker ─────────────────────────────────────────────
@pytest.mark.asyncio
class TestAvailabilityChecker:
    async def test_check_health(self, db, orch_env):
        result = await check_health(db, company_id=orch_env["company_id"])
        assert result.status == CheckStatus.PASS

    async def test_check_workspace_empty(self, db, orch_env):
        result = await check_workspace(db, company_id=orch_env["company_id"])
        assert result.status == CheckStatus.FAIL

    async def test_check_concurrency_slot_available(self, db, orch_env):
        result = await check_concurrency_slot(db, company_id=orch_env["company_id"], max_concurrent=5)
        assert result.status == CheckStatus.PASS
        assert "5 slot(s)" in result.message

    async def test_check_model(self, db):
        result = await check_model(db, provider="openai", model="gpt-4o")
        assert result.status == CheckStatus.PASS

    async def test_run_availability_checks_minimal(self, db, orch_env):
        report = await run_availability_checks(
            db,
            company_id=orch_env["company_id"],
        )
        assert isinstance(report, AvailabilityReport)
        assert len(report.checks) >= 3
