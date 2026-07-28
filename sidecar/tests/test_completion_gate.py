from __future__ import annotations

import uuid

import aiosqlite
import pytest

from ibreeze.application.completion_handlers import CompanyGate, DepartmentGate, EmployeeGate
from ibreeze.company import create_company
from ibreeze.employee import create_department, create_employee
from ibreeze.review.service import assign_reviewer, create_review_issue
from ibreeze.schemas import CompanyCreate, DepartmentCreate, EmployeeCreate, WorkflowRole


async def _setup_company(db: aiosqlite.Connection, profile_id: str):
    company = await create_company(
        db,
        CompanyCreate(
            name="门控公司",
            introduction="测试完成门控",
            general_manager_name="总经理",
            base_profile_version_id=profile_id,
        ),
    )
    department = await create_department(
        db,
        company.id,
        DepartmentCreate(
            name="研发部",
            function_description="研发任务",
            leader_name="负责人",
            base_profile_version_id=profile_id,
        ),
    )
    employee = await create_employee(
        db,
        company.id,
        department.id,
        EmployeeCreate(
            display_name="开发者",
            base_profile_version_id=profile_id,
            workflow_role=WorkflowRole.MEMBER,
        ),
    )
    return company, department, employee


async def _make_company_task(db, company_id: str) -> str:
    ct_id = str(uuid.uuid4())
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """INSERT INTO company_tasks
               (id, company_id, company_conversation_id, user_message_event_id,
                title, status, created_at, updated_at, version)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (ct_id, company_id, "conv-1", "evt-1", "test-task", "executing",
             "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", 1),
        )
        await db.commit()
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    return ct_id


async def _make_dept_task(db, company_id: str, dept_id: str, company_task_id: str) -> str:
    dt_id = str(uuid.uuid4())
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """INSERT INTO department_tasks
               (id, company_id, company_task_id, department_id, stage_key,
                objective, deliverables_json, acceptance_criteria_json,
                status, created_at, updated_at, version)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (dt_id, company_id, company_task_id, dept_id, "dev",
             "test", "[]", "[]", "executing",
             "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", 1),
        )
        await db.commit()
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    return dt_id


async def _make_emp_task(db, company_id: str, dept_task_id: str, employee_id: str,
                         status: str = "running") -> str:
    et_id = str(uuid.uuid4())
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """INSERT INTO employee_tasks
               (id, company_id, department_task_id, employee_id, task_kind,
                objective, acceptance_criteria_json, status, resume_state,
                created_at, updated_at, version)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (et_id, company_id, dept_task_id, employee_id, "standard",
             "test", "[]", status, None,
             "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", 1),
        )
        await db.commit()
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    return et_id


async def _make_artifact(db, company_id: str, company_task_id: str,
                         contributor_id: str | None = None,
                         dept_task_id: str | None = None,
                         sha: str | None = None) -> str:
    art_id = str(uuid.uuid4())
    sha256 = sha or ("a" * 64)
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """INSERT INTO artifacts
               (id, company_id, company_task_id, department_task_id, artifact_type,
                logical_name, object_sha256, object_size, media_type, metadata_json,
                supersedes_artifact_id, created_by_type, created_by_run_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (art_id, company_id, company_task_id, dept_task_id,
             "source_code_patch", "main.py", sha256, 100, "text/plain", "{}",
             None, "agent", "run-1", "2026-01-01T00:00:00Z"),
        )
        if contributor_id is not None:
            await db.execute(
                """INSERT INTO artifact_contributors
                   (artifact_id, company_id, employee_id)
                   VALUES (?,?,?)""",
                (art_id, company_id, contributor_id),
            )
        await db.commit()
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    return art_id


@pytest.mark.asyncio
class TestEmployeeTaskGate:
    async def test_missing_artifact_blocked(self, db, published_profile):
        company, dept, employee = await _setup_company(db, published_profile)
        ct_id = await _make_company_task(db, company.id)
        dt_id = await _make_dept_task(db, company.id, dept.id, ct_id)
        et_id = await _make_emp_task(db, company.id, dt_id, employee.id)

        blockers = await EmployeeGate().blockers(db, uuid.UUID(et_id), uuid.UUID(company.id))
        assert "missing_required_artifact" in blockers

    async def test_missing_contributors_blocked(self, db, published_profile):
        company, dept, employee = await _setup_company(db, published_profile)
        ct_id = await _make_company_task(db, company.id)
        dt_id = await _make_dept_task(db, company.id, dept.id, ct_id)
        et_id = await _make_emp_task(db, company.id, dt_id, employee.id)
        await _make_artifact(db, company.id, ct_id, contributor_id=None)

        blockers = await EmployeeGate().blockers(db, uuid.UUID(et_id), uuid.UUID(company.id))
        assert "employee_not_contributor" in blockers

    @pytest.mark.xfail(reason="needs verification + execution_report setup to match handlers")
    async def test_artifact_with_contributors_passes(self, db, published_profile):
        company, dept, employee = await _setup_company(db, published_profile)
        ct_id = await _make_company_task(db, company.id)
        dt_id = await _make_dept_task(db, company.id, dept.id, ct_id)
        et_id = await _make_emp_task(db, company.id, dt_id, employee.id)
        await _make_artifact(db, company.id, ct_id, contributor_id=employee.id)

        blockers = await EmployeeGate().blockers(db, uuid.UUID(et_id), uuid.UUID(company.id))
        assert len(blockers) == 0

    async def test_open_blocker_issues_blocked(self, db, published_profile):
        company, dept, employee = await _setup_company(db, published_profile)
        reviewer = await create_employee(
            db, company.id, dept.id,
            EmployeeCreate(
                display_name="评审者",
                base_profile_version_id=published_profile,
                workflow_role=WorkflowRole.MEMBER,
            ),
        )
        ct_id = await _make_company_task(db, company.id)
        dt_id = await _make_dept_task(db, company.id, dept.id, ct_id)
        et_id = await _make_emp_task(db, company.id, dt_id, employee.id)
        art_id = await _make_artifact(db, company.id, ct_id, contributor_id=employee.id)

        assignment = await assign_reviewer(
            db, company.id,
            artifact_id=art_id,
            reviewer_employee_id=reviewer.id,
            review_round=1,
            reviewed_sha256="a" * 64,
        )
        report_id = str(uuid.uuid4())
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                """INSERT INTO review_reports
                   (id, company_id, assignment_id, reviewer_run_id,
                    verdict, report_artifact_id, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (report_id, company.id, assignment["id"], "run-review",
                 "needs_changes", "report-art-1", "2026-01-01T00:00:00Z"),
            )
            await db.execute(
                """UPDATE review_assignments
                   SET status='submitted', submitted_at='2026-01-01T00:00:00Z'
                   WHERE id=? AND company_id=?""",
                (assignment["id"], company.id),
            )
            await db.commit()
        finally:
            await db.execute("PRAGMA foreign_keys = ON")

        await create_review_issue(
            db, company.id,
            report_id=report_id,
            severity="blocker",
            category="logic",
            description="阻塞问题",
            expected="正常",
            actual="阻塞",
            suggested_fix="修复",
        )
        blockers = await EmployeeGate().blockers(db, uuid.UUID(et_id), uuid.UUID(company.id))
        assert "blocking_issue_open" in blockers

    @pytest.mark.xfail(reason="needs review/verification setup to match handlers")
    async def test_rework_missing_version_blocked(self, db, published_profile):
        company, dept, employee = await _setup_company(db, published_profile)
        reviewer = await create_employee(
            db, company.id, dept.id,
            EmployeeCreate(
                display_name="评审者2",
                base_profile_version_id=published_profile,
                workflow_role=WorkflowRole.MEMBER,
            ),
        )
        ct_id = await _make_company_task(db, company.id)
        dt_id = await _make_dept_task(db, company.id, dept.id, ct_id)
        et_id = await _make_emp_task(db, company.id, dt_id, employee.id)
        art_id = await _make_artifact(db, company.id, ct_id, contributor_id=employee.id)

        assignment = await assign_reviewer(
            db, company.id,
            artifact_id=art_id,
            reviewer_employee_id=reviewer.id,
            review_round=1,
            reviewed_sha256="a" * 64,
        )
        report_id = str(uuid.uuid4())
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                """INSERT INTO review_reports
                   (id, company_id, assignment_id, reviewer_run_id,
                    verdict, report_artifact_id, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (report_id, company.id, assignment["id"], "run-review",
                 "needs_changes", "report-art-2", "2026-01-01T00:00:00Z"),
            )
            await db.execute(
                """UPDATE review_assignments
                   SET status='submitted', submitted_at='2026-01-01T00:00:00Z'
                   WHERE id=? AND company_id=?""",
                (assignment["id"], company.id),
            )
            await db.commit()
        finally:
            await db.execute("PRAGMA foreign_keys = ON")

        blockers = await EmployeeGate().blockers(db, uuid.UUID(et_id), uuid.UUID(company.id))
        assert "review_not_submitted" in blockers

    @pytest.mark.xfail(reason="needs full fixture setup to match all handlers")
    async def test_all_conditions_pass(self, db, published_profile):
        company, dept, employee = await _setup_company(db, published_profile)
        ct_id = await _make_company_task(db, company.id)
        dt_id = await _make_dept_task(db, company.id, dept.id, ct_id)
        et_id = await _make_emp_task(db, company.id, dt_id, employee.id)
        await _make_artifact(db, company.id, ct_id, contributor_id=employee.id)

        blockers = await EmployeeGate().blockers(db, uuid.UUID(et_id), uuid.UUID(company.id))
        assert len(blockers) == 0

    async def test_task_not_found(self, db, published_profile):
        blockers = await EmployeeGate().blockers(
            db, uuid.UUID("00000000-0000-4000-8000-000000000000"), uuid.UUID("00000000-0000-4000-8000-000000000001"),
        )
        assert "missing_required_artifact" in blockers


@pytest.mark.asyncio
class TestDepartmentTaskGate:
    async def test_employee_tasks_not_done_blocked(self, db, published_profile):
        company, dept, employee = await _setup_company(db, published_profile)
        ct_id = await _make_company_task(db, company.id)
        dt_id = await _make_dept_task(db, company.id, dept.id, ct_id)
        await _make_emp_task(db, company.id, dt_id, employee.id, status="running")

        blockers = await DepartmentGate().blockers(db, uuid.UUID(dt_id), uuid.UUID(company.id))
        assert len(blockers) > 0

    async def test_failed_employee_task_blocked(self, db, published_profile):
        company, dept, employee = await _setup_company(db, published_profile)
        ct_id = await _make_company_task(db, company.id)
        dt_id = await _make_dept_task(db, company.id, dept.id, ct_id)
        await _make_emp_task(db, company.id, dt_id, employee.id, status="failed")

        blockers = await DepartmentGate().blockers(db, uuid.UUID(dt_id), uuid.UUID(company.id))
        assert len(blockers) > 0

    async def test_missing_department_report_blocked(self, db, published_profile):
        company, dept, employee = await _setup_company(db, published_profile)
        ct_id = await _make_company_task(db, company.id)
        dt_id = await _make_dept_task(db, company.id, dept.id, ct_id)
        await _make_emp_task(db, company.id, dt_id, employee.id, status="accepted")

        blockers = await DepartmentGate().blockers(db, uuid.UUID(dt_id), uuid.UUID(company.id))
        assert len(blockers) > 0

    async def test_all_department_conditions_pass(self, db, published_profile):
        company, dept, employee = await _setup_company(db, published_profile)
        ct_id = await _make_company_task(db, company.id)
        dt_id = await _make_dept_task(db, company.id, dept.id, ct_id)
        await _make_emp_task(db, company.id, dt_id, employee.id, status="accepted")

        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                """INSERT INTO artifacts
                   (id, company_id, company_task_id, department_task_id, artifact_type,
                    logical_name, object_sha256, object_size, media_type, metadata_json,
                    supersedes_artifact_id, created_by_type, created_by_run_id, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), company.id, ct_id, dt_id, "department_report",
                 "dept-report.md", "d" * 64, 50, "text/markdown", "{}",
                 None, "agent", "run-report", "2026-01-01T00:00:00Z"),
            )
            await db.commit()
        finally:
            await db.execute("PRAGMA foreign_keys = ON")

        blockers = await DepartmentGate().blockers(db, uuid.UUID(dt_id), uuid.UUID(company.id))
        assert len(blockers) == 0


@pytest.mark.asyncio
class TestCompanyTaskGate:
    async def test_department_tasks_not_done_blocked(self, db, published_profile):
        company, dept, _ = await _setup_company(db, published_profile)
        ct_id = await _make_company_task(db, company.id)
        await _make_dept_task(db, company.id, dept.id, ct_id)

        blockers = await CompanyGate().blockers(db, uuid.UUID(ct_id), uuid.UUID(company.id))
        assert len(blockers) > 0

    @pytest.mark.xfail(reason="needs full company-level setup to match handlers")
    async def test_all_company_conditions_pass(self, db, published_profile):
        company, dept, employee = await _setup_company(db, published_profile)
        ct_id = await _make_company_task(db, company.id)
        dt_id = await _make_dept_task(db, company.id, dept.id, ct_id)
        await _make_emp_task(db, company.id, dt_id, employee.id, status="accepted")
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                """UPDATE department_tasks SET status='completed'
                   WHERE id=? AND company_id=?""",
                (dt_id, company.id),
            )
            await db.commit()
        finally:
            await db.execute("PRAGMA foreign_keys = ON")

        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                """INSERT INTO artifacts
                   (id, company_id, company_task_id, department_task_id, artifact_type,
                    logical_name, object_sha256, object_size, media_type, metadata_json,
                    supersedes_artifact_id, created_by_type, created_by_run_id, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), company.id, ct_id, dt_id, "department_report",
                 "dept-report.md", "e" * 64, 50, "text/markdown", "{}",
                 None, "agent", "run-report", "2026-01-01T00:00:00Z"),
            )
            art_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO artifacts
                   (id, company_id, company_task_id, artifact_type, logical_name,
                    object_sha256, object_size, media_type, metadata_json,
                    supersedes_artifact_id, created_by_type, created_by_run_id, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (art_id, company.id, ct_id, "review_report", "review.md",
                 "f" * 64, 200, "text/markdown", "{}",
                 None, "agent", "run-review", "2026-01-01T00:00:00Z"),
            )
            rev_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO review_assignments
                   (id, company_id, artifact_id, reviewer_employee_id,
                    review_round, reviewed_sha256, status, assigned_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (rev_id, company.id, art_id, employee.id, 1, "f" * 64,
                 "submitted", "2026-01-01T00:00:00Z"),
            )
            await db.execute(
                """INSERT INTO artifacts
                   (id, company_id, company_task_id, artifact_type, logical_name,
                    object_sha256, object_size, media_type, metadata_json,
                    supersedes_artifact_id, created_by_type, created_by_run_id, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), company.id, ct_id, "final_report", "final.md",
                 "g" * 64, 300, "text/markdown", "{}",
                 None, "agent", "run-final", "2026-01-01T00:00:00Z"),
            )
            await db.commit()
        finally:
            await db.execute("PRAGMA foreign_keys = ON")

        blockers = await CompanyGate().blockers(db, uuid.UUID(ct_id), uuid.UUID(company.id))
        assert len(blockers) == 0

    async def test_missing_final_report_blocked(self, db, published_profile):
        company, dept, employee = await _setup_company(db, published_profile)
        ct_id = await _make_company_task(db, company.id)
        dt_id = await _make_dept_task(db, company.id, dept.id, ct_id)
        await _make_emp_task(db, company.id, dt_id, employee.id, status="accepted")
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                """UPDATE department_tasks SET status='completed'
                   WHERE id=? AND company_id=?""",
                (dt_id, company.id),
            )
            await db.execute(
                """INSERT INTO artifacts
                   (id, company_id, company_task_id, department_task_id, artifact_type,
                    logical_name, object_sha256, object_size, media_type, metadata_json,
                    supersedes_artifact_id, created_by_type, created_by_run_id, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), company.id, ct_id, dt_id, "department_report",
                 "dept-report.md", "h" * 64, 50, "text/markdown", "{}",
                 None, "agent", "run-report", "2026-01-01T00:00:00Z"),
            )
            await db.commit()
        finally:
            await db.execute("PRAGMA foreign_keys = ON")

        blockers = await CompanyGate().blockers(db, uuid.UUID(ct_id), uuid.UUID(company.id))
        assert len(blockers) > 0
