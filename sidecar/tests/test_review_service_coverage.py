"""Coverage-focused tests for ``ibreeze.review.service``.

Targets the uncovered branches of the review assignment / report service:

- ``assign_reviewer`` guards (ARTIFACT_NOT_FOUND, ARTIFACT_SHA_MISMATCH,
  REVIEWER_NOT_AVAILABLE)
- ``assign_existing_reviewer`` (every branch, including the optimistic lock)
- ``start_review`` happy path + STATE_TRANSITION_INVALID
- ``submit_review_report`` happy path (with issues and with a superseding
  artifact -> stale), plus every guard
- ``start_fixing_review_issue`` STATE_TRANSITION_INVALID

Database-backed branches use the shared ``db`` / ``published_profile`` fixtures
following the style of ``test_review_advanced.py``; the optimistic-lock
branches are exercised through a mock session that dispatches on SQL text.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from ibreeze.company import create_company
from ibreeze.employee import create_department, create_employee
from ibreeze.review.service import (
    assign_existing_reviewer,
    assign_reviewer,
    create_review_issue,
    start_fixing_review_issue,
    start_review,
    submit_review_report,
)
from ibreeze.schemas import CompanyCreate, DepartmentCreate, EmployeeCreate, WorkflowRole

_NOW = "2026-01-01T00:00:00Z"
_SHA = "a" * 64


async def _setup_review_scenario(db, profile_id: str) -> dict:
    """Company + department + contributor + reviewer + artifact + agent run
    + a review-report artifact, all ready for the full submit flow."""
    await db.execute("BEGIN IMMEDIATE")
    try:
        company = await create_company(
            db,
            CompanyCreate(
                name="评审公司",
                introduction="测试评审流程",
                general_manager_name="总经理",
                base_profile_version_id=profile_id,
            ),
        )
        department = await create_department(
            db,
            company.id,
            DepartmentCreate(
                name="开发部",
                function_description="实现代码",
                leader_name="负责人",
                base_profile_version_id=profile_id,
            ),
        )
        contributor = await create_employee(
            db,
            company.id,
            department.id,
            EmployeeCreate(
                display_name="开发者",
                base_profile_version_id=profile_id,
                workflow_role=WorkflowRole.MEMBER,
            ),
        )
        reviewer = await create_employee(
            db,
            company.id,
            department.id,
            EmployeeCreate(
                display_name="评审者",
                base_profile_version_id=profile_id,
                workflow_role=WorkflowRole.MEMBER,
            ),
        )
        artifact_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        report_artifact_id = str(uuid.uuid4())
        await db.commit()
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                """INSERT INTO artifacts
                   (id, company_id, company_task_id, artifact_type, logical_name,
                    object_sha256, object_size, media_type, metadata_json,
                    supersedes_artifact_id, created_by_type, created_by_run_id, created_at)
                   VALUES (?,?,?,'source_code_patch','main.py',?,100,'text/plain','{}',NULL,'system',NULL,?)""",
                (artifact_id, company.id, task_id, _SHA, _NOW),
            )
            await db.execute(
                """INSERT INTO artifact_contributors
                   (artifact_id, company_id, employee_id) VALUES (?,?,?)""",
                (artifact_id, company.id, contributor.id),
            )
            await db.execute(
                """INSERT INTO agent_runs
                   (id, company_id, company_task_id, work_item_id, employee_id,
                    conversation_id, availability_snapshot_id, execution_snapshot_id,
                    run_purpose, adapter_type, run_spec_json, run_spec_sha256,
                    status, attempt, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,'review','codex_cli','{}',?,'succeeded',1,?,?)""",
                (
                    run_id,
                    company.id,
                    task_id,
                    task_id,
                    reviewer.id,
                    str(uuid.uuid4()),
                    str(uuid.uuid4()),
                    str(uuid.uuid4()),
                    "a" * 64,
                    _NOW,
                    _NOW,
                ),
            )
            await db.execute(
                """INSERT INTO artifacts
                   (id, company_id, company_task_id, artifact_type, logical_name,
                    object_sha256, object_size, media_type, metadata_json,
                    supersedes_artifact_id, created_by_type, created_by_run_id, created_at)
                   VALUES (?,?,?,'review_report','report.md',?,10,'text/markdown','{}',NULL,'agent',?,?)""",
                (report_artifact_id, company.id, task_id, _SHA, run_id, _NOW),
            )
            await db.commit()
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        await db.commit()
        return {
            "company": company,
            "contributor": contributor,
            "reviewer": reviewer,
            "artifact_id": artifact_id,
            "sha256": _SHA,
            "task_id": task_id,
            "run_id": run_id,
            "report_artifact_id": report_artifact_id,
        }
    except Exception:
        await db.rollback()
        raise


async def _assign(db, scenario: dict, *, round_no: int = 1) -> dict:
    return await assign_reviewer(
        db,
        scenario["company"].id,
        artifact_id=scenario["artifact_id"],
        reviewer_employee_id=scenario["reviewer"].id,
        review_round=round_no,
        reviewed_sha256=scenario["sha256"],
    )


async def _insert_assignment_direct(
    db,
    scenario: dict,
    *,
    artifact_id: str | None = None,
    reviewed_sha256: str | None = None,
    reviewer_employee_id: str | None = None,
) -> str:
    """Insert a review_assignment bypassing assign_reviewer (for guards that
    need a mismatched artifact/reviewer binding)."""
    assignment_id = str(uuid.uuid4())
    await db.commit()
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """INSERT INTO review_assignments
               (id, company_id, artifact_id, reviewer_employee_id, review_round,
                reviewed_sha256, status, assigned_at)
               VALUES (?,?,?,?,1,?,'assigned',?)""",
            (
                assignment_id,
                scenario["company"].id,
                artifact_id or scenario["artifact_id"],
                reviewer_employee_id or scenario["reviewer"].id,
                reviewed_sha256 or scenario["sha256"],
                _NOW,
            ),
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()
    return assignment_id


async def _create_report_direct(db, company_id: str, assignment_id: str) -> str:
    """Create a review_report directly, bypassing the guarded submit flow."""
    await db.commit()
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        report_id = str(uuid.uuid4())
        assignment = await (
            await db.execute(
                "SELECT artifact_id, reviewed_sha256 FROM review_assignments WHERE id=? AND company_id=?",
                (assignment_id, company_id),
            )
        ).fetchone()
        assert assignment is not None
        await db.execute(
            """INSERT INTO review_reports
               (id, company_id, assignment_id, reviewer_run_id,
                reviewed_artifact_id, reviewed_sha256, verdict,
                report_artifact_id, version, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                report_id,
                company_id,
                assignment_id,
                "run-fake",
                assignment["artifact_id"],
                assignment["reviewed_sha256"],
                "needs_changes",
                "report-direct",
                1,
                _NOW,
            ),
        )
        await db.execute(
            """UPDATE review_assignments
               SET status='submitted', submitted_at=?
               WHERE id=? AND company_id=?""",
            (_NOW, assignment_id, company_id),
        )
        await db.commit()
        return report_id
    finally:
        await db.execute("PRAGMA foreign_keys = ON")


def _make_cursor(row: object = None, *, rowcount: int = 1) -> AsyncMock:
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=row)
    cursor.rowcount = rowcount
    return cursor


def _assignment_row(*, status: str = "assigned", version: int = 1) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "artifact_id": str(uuid.uuid4()),
        "reviewed_sha256": _SHA,
        "reviewer_employee_id": str(uuid.uuid4()),
        "status": status,
        "version": version,
    }


@pytest.mark.asyncio
class TestAssignReviewerErrors:
    async def test_artifact_not_found(self, db, published_profile):
        scenario = await _setup_review_scenario(db, published_profile)

        with pytest.raises(ValueError, match="ARTIFACT_NOT_FOUND"):
            await assign_reviewer(
                db,
                scenario["company"].id,
                artifact_id="missing-artifact",
                reviewer_employee_id=scenario["reviewer"].id,
                review_round=1,
                reviewed_sha256=_SHA,
            )

    async def test_artifact_sha_mismatch(self, db, published_profile):
        scenario = await _setup_review_scenario(db, published_profile)

        with pytest.raises(ValueError, match="ARTIFACT_SHA_MISMATCH"):
            await assign_reviewer(
                db,
                scenario["company"].id,
                artifact_id=scenario["artifact_id"],
                reviewer_employee_id=scenario["reviewer"].id,
                review_round=1,
                reviewed_sha256="b" * 64,
            )

    async def test_reviewer_not_available(self, db, published_profile):
        scenario = await _setup_review_scenario(db, published_profile)

        with pytest.raises(ValueError, match="REVIEWER_NOT_AVAILABLE"):
            await assign_reviewer(
                db,
                scenario["company"].id,
                artifact_id=scenario["artifact_id"],
                reviewer_employee_id="no-such-employee",
                review_round=1,
                reviewed_sha256=_SHA,
            )


class TestAssignExistingReviewer:
    def _session(
        self,
        *,
        assignment_row: dict | None,
        reviewer_row: object = None,
        contributor_row: object = None,
        update_rowcount: int = 1,
    ) -> AsyncMock:
        async def execute(sql, parameters=()):
            if "FROM review_assignments" in sql:
                return _make_cursor(assignment_row)
            if "FROM employees" in sql:
                return _make_cursor(reviewer_row)
            if "artifact_contributors" in sql:
                return _make_cursor(contributor_row)
            if sql.lstrip().startswith("UPDATE"):
                return _make_cursor(rowcount=update_rowcount)
            return _make_cursor()

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=execute)
        return session

    async def test_binds_reviewer(self):
        row = _assignment_row(status="assigned", version=1)
        session = self._session(assignment_row=row, reviewer_row={"1": 1})

        result = await assign_existing_reviewer(
            session,
            str(uuid.uuid4()),
            assignment_id=row["id"],
            reviewer_employee_id=row["reviewer_employee_id"],
        )

        assert result == {"success": True, "version": 2}

    async def test_binds_in_review_assignment(self):
        row = _assignment_row(status="in_review", version=3)
        session = self._session(assignment_row=row, reviewer_row={"1": 1})

        result = await assign_existing_reviewer(
            session, str(uuid.uuid4()), assignment_id=row["id"], reviewer_employee_id="x"
        )

        assert result == {"success": True, "version": 4}

    async def test_resource_not_found(self):
        session = self._session(assignment_row=None)

        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await assign_existing_reviewer(session, str(uuid.uuid4()), assignment_id="x", reviewer_employee_id="y")

    async def test_state_transition_invalid(self):
        row = _assignment_row(status="submitted", version=1)
        session = self._session(assignment_row=row)

        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await assign_existing_reviewer(session, str(uuid.uuid4()), assignment_id=row["id"], reviewer_employee_id="y")

    async def test_reviewer_not_available(self):
        row = _assignment_row(status="assigned", version=1)
        session = self._session(assignment_row=row, reviewer_row=None)

        with pytest.raises(ValueError, match="REVIEWER_NOT_AVAILABLE"):
            await assign_existing_reviewer(session, str(uuid.uuid4()), assignment_id=row["id"], reviewer_employee_id="y")

    async def test_reviewer_cannot_be_contributor(self):
        row = _assignment_row(status="assigned", version=1)
        session = self._session(assignment_row=row, reviewer_row={"1": 1}, contributor_row={"1": 1})

        with pytest.raises(ValueError, match="REVIEWER_CANNOT_BE_CONTRIBUTOR"):
            await assign_existing_reviewer(session, str(uuid.uuid4()), assignment_id=row["id"], reviewer_employee_id="y")

    async def test_optimistic_lock_conflict(self):
        row = _assignment_row(status="assigned", version=1)
        session = self._session(assignment_row=row, reviewer_row={"1": 1}, update_rowcount=0)

        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await assign_existing_reviewer(session, str(uuid.uuid4()), assignment_id=row["id"], reviewer_employee_id="y")


@pytest.mark.asyncio
class TestStartReview:
    async def test_starts_review(self, db, published_profile):
        scenario = await _setup_review_scenario(db, published_profile)
        assignment = await _assign(db, scenario)

        result = await start_review(db, scenario["company"].id, assignment_id=assignment["id"])

        assert result["status"] == "in_review"
        row = await (
            await db.execute("SELECT status FROM review_assignments WHERE id=?", (assignment["id"],))
        ).fetchone()
        assert row["status"] == "in_review"

    async def test_state_transition_invalid(self, db, published_profile):
        scenario = await _setup_review_scenario(db, published_profile)
        assignment = await _assign(db, scenario)
        await start_review(db, scenario["company"].id, assignment_id=assignment["id"])

        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await start_review(db, scenario["company"].id, assignment_id=assignment["id"])


@pytest.mark.asyncio
class TestSubmitReviewReport:
    def _submit_kwargs(self, scenario: dict, assignment: dict, **overrides) -> dict:
        kwargs = {
            "db": None,  # filled by the caller
            "company_id": scenario["company"].id,
            "assignment_id": assignment["id"],
            "artifact_id": scenario["artifact_id"],
            "artifact_sha256": scenario["sha256"],
            "report_artifact_id": scenario["report_artifact_id"],
            "reviewer_run_id": scenario["run_id"],
            "verdict": "pass",
            "summary": "looks good",
        }
        kwargs.update(overrides)
        return kwargs

    async def test_submits_report(self, db, published_profile):
        scenario = await _setup_review_scenario(db, published_profile)
        assignment = await _assign(db, scenario)
        kwargs = self._submit_kwargs(scenario, assignment, db=db)

        result = await submit_review_report(**kwargs)

        assert result["status"] == "submitted"
        assert result["verdict"] == "pass"
        report = await (
            await db.execute("SELECT verdict FROM review_reports WHERE assignment_id=?", (assignment["id"],))
        ).fetchone()
        assert report["verdict"] == "pass"
        status = await (
            await db.execute("SELECT status FROM review_assignments WHERE id=?", (assignment["id"],))
        ).fetchone()
        assert status["status"] == "submitted"

    async def test_submits_report_with_issues(self, db, published_profile):
        scenario = await _setup_review_scenario(db, published_profile)
        assignment = await _assign(db, scenario)
        issues = [
            {
                "severity": "high",
                "category": "security",
                "description": "danger",
                "expected": "safe",
                "actual": "unsafe",
                "suggested_fix": "patch it",
                "evidence_refs": [scenario["artifact_id"]],
            },
            {"severity": "low", "category": "style", "description": "typo"},
        ]
        kwargs = self._submit_kwargs(scenario, assignment, db=db, verdict="needs_changes", issues=issues)

        result = await submit_review_report(**kwargs)

        assert result["status"] == "submitted"
        rows = await (
            await db.execute(
                "SELECT severity, category, evidence_refs_json FROM review_issues WHERE company_id=?",
                (scenario["company"].id,),
            )
        ).fetchall()
        assert len(rows) == 2
        severities = {row["severity"] for row in rows}
        assert severities == {"high", "low"}
        assert any(scenario["artifact_id"] in row["evidence_refs_json"] for row in rows)

    async def test_superseding_artifact_marks_assignment_stale(self, db, published_profile):
        scenario = await _setup_review_scenario(db, published_profile)
        assignment = await _assign(db, scenario)
        superseding_id = str(uuid.uuid4())
        await db.commit()
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                """INSERT INTO artifacts
                   (id, company_id, company_task_id, artifact_type, logical_name,
                    object_sha256, object_size, media_type, metadata_json,
                    supersedes_artifact_id, created_by_type, created_by_run_id, created_at)
                   VALUES (?,?,?,'source_code_patch','new.py',?,10,'text/plain','{}',?,'user',NULL,?)""",
                (superseding_id, scenario["company"].id, scenario["task_id"], "c" * 64, scenario["artifact_id"], _NOW),
            )
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        # The supersede trigger flipped the original artifact to is_current=0; restore it.
        await db.execute(
            "UPDATE artifacts SET is_current=1 WHERE id=? AND company_id=?",
            (scenario["artifact_id"], scenario["company"].id),
        )
        await db.commit()

        result = await submit_review_report(
            db,
            scenario["company"].id,
            assignment_id=assignment["id"],
            artifact_id=scenario["artifact_id"],
            artifact_sha256=scenario["sha256"],
            report_artifact_id=scenario["report_artifact_id"],
            reviewer_run_id=scenario["run_id"],
            verdict="pass",
            summary="x",
        )

        assert result["status"] == "stale"
        row = await (
            await db.execute("SELECT status FROM review_assignments WHERE id=?", (assignment["id"],))
        ).fetchone()
        assert row["status"] == "stale"

    async def test_reviewer_run_id_required(self, db, published_profile):
        scenario = await _setup_review_scenario(db, published_profile)
        assignment = await _assign(db, scenario)

        with pytest.raises(ValueError, match="REVIEWER_RUN_ID_REQUIRED"):
            await submit_review_report(
                db,
                scenario["company"].id,
                assignment_id=assignment["id"],
                artifact_id=scenario["artifact_id"],
                artifact_sha256=scenario["sha256"],
                report_artifact_id=scenario["report_artifact_id"],
                reviewer_run_id=None,
                verdict="pass",
                summary="x",
            )

    async def test_artifact_not_found(self, db, published_profile):
        scenario = await _setup_review_scenario(db, published_profile)
        assignment_id = await _insert_assignment_direct(db, scenario, artifact_id="missing-artifact")

        with pytest.raises(ValueError, match="ARTIFACT_NOT_FOUND"):
            await submit_review_report(
                db,
                scenario["company"].id,
                assignment_id=assignment_id,
                artifact_id="missing-artifact",
                artifact_sha256=_SHA,
                report_artifact_id="x",
                reviewer_run_id="run-x",
                verdict="pass",
                summary="x",
            )

    async def test_artifact_sha_mismatch(self, db, published_profile):
        scenario = await _setup_review_scenario(db, published_profile)
        assignment_id = await _insert_assignment_direct(db, scenario, reviewed_sha256="b" * 64)

        with pytest.raises(ValueError, match="ARTIFACT_SHA_MISMATCH"):
            await submit_review_report(
                db,
                scenario["company"].id,
                assignment_id=assignment_id,
                artifact_id=scenario["artifact_id"],
                artifact_sha256="b" * 64,
                report_artifact_id="x",
                reviewer_run_id="run-x",
                verdict="pass",
                summary="x",
            )

    async def test_report_artifact_mismatch(self, db, published_profile):
        scenario = await _setup_review_scenario(db, published_profile)
        assignment = await _assign(db, scenario)

        with pytest.raises(ValueError, match="REVIEW_REPORT_ARTIFACT_MISMATCH"):
            await submit_review_report(
                db,
                scenario["company"].id,
                assignment_id=assignment["id"],
                artifact_id=scenario["artifact_id"],
                artifact_sha256=scenario["sha256"],
                report_artifact_id="missing-report",
                reviewer_run_id=scenario["run_id"],
                verdict="pass",
                summary="x",
            )

    async def test_run_binding_mismatch(self, db, published_profile):
        scenario = await _setup_review_scenario(db, published_profile)
        ghost_run_id = str(uuid.uuid4())
        ghost_report_id = str(uuid.uuid4())
        await db.commit()
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                """INSERT INTO artifacts
                   (id, company_id, company_task_id, artifact_type, logical_name,
                    object_sha256, object_size, media_type, metadata_json,
                    supersedes_artifact_id, created_by_type, created_by_run_id, created_at)
                   VALUES (?,?,?,'review_report','ghost.md',?,10,'text/markdown','{}',NULL,'agent',?,?)""",
                (ghost_report_id, scenario["company"].id, scenario["task_id"], _SHA, ghost_run_id, _NOW),
            )
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        await db.commit()
        assignment = await _assign(db, scenario)

        with pytest.raises(ValueError, match="REVIEW_RUN_BINDING_MISMATCH"):
            await submit_review_report(
                db,
                scenario["company"].id,
                assignment_id=assignment["id"],
                artifact_id=scenario["artifact_id"],
                artifact_sha256=scenario["sha256"],
                report_artifact_id=ghost_report_id,
                reviewer_run_id=ghost_run_id,
                verdict="pass",
                summary="x",
            )

    async def test_reviewer_cannot_be_contributor(self, db, published_profile):
        scenario = await _setup_review_scenario(db, published_profile)
        assignment = await _assign(db, scenario)
        await db.execute(
            "INSERT INTO artifact_contributors (artifact_id, company_id, employee_id) VALUES (?,?,?)",
            (scenario["artifact_id"], scenario["company"].id, scenario["reviewer"].id),
        )
        await db.commit()

        with pytest.raises(ValueError, match="REVIEWER_CANNOT_BE_CONTRIBUTOR"):
            await submit_review_report(
                db,
                scenario["company"].id,
                assignment_id=assignment["id"],
                artifact_id=scenario["artifact_id"],
                artifact_sha256=scenario["sha256"],
                report_artifact_id=scenario["report_artifact_id"],
                reviewer_run_id=scenario["run_id"],
                verdict="pass",
                summary="x",
            )

    async def test_optimistic_lock_conflict(self):
        """Final assignment UPDATE misses -> OPTIMISTIC_LOCK_CONFLICT."""
        company_id = str(uuid.uuid4())
        row = _assignment_row(status="assigned", version=1)

        async def execute(sql, parameters=()):
            if "artifact_contributors" in sql:
                return _make_cursor(None)
            if "FROM review_assignments" in sql:
                return _make_cursor(row)
            if "object_sha256" in sql:
                return _make_cursor({"object_sha256": _SHA, "is_current": 1})
            if "artifact_type" in sql:
                return _make_cursor({"artifact_type": "review_report", "created_by_type": "agent", "created_by_run_id": "run-1"})
            if "FROM agent_runs" in sql:
                return _make_cursor({"employee_id": row["reviewer_employee_id"], "run_purpose": "review", "status": "succeeded"})
            if "supersedes_artifact_id" in sql:
                return _make_cursor(None)
            if sql.lstrip().startswith("INSERT"):
                return _make_cursor()
            if sql.lstrip().startswith("UPDATE"):
                return _make_cursor(rowcount=0)
            return _make_cursor()

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=execute)

        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await submit_review_report(
                session,
                company_id,
                assignment_id=row["id"],
                artifact_id=row["artifact_id"],
                artifact_sha256=row["reviewed_sha256"],
                report_artifact_id="report-1",
                reviewer_run_id="run-1",
                verdict="pass",
                summary="x",
            )


@pytest.mark.asyncio
class TestStartFixingReviewIssue:
    async def test_state_transition_invalid(self, db, published_profile):
        scenario = await _setup_review_scenario(db, published_profile)
        assignment = await _assign(db, scenario)
        report_id = await _create_report_direct(db, scenario["company"].id, assignment["id"])
        issue = await create_review_issue(
            db,
            scenario["company"].id,
            report_id=report_id,
            severity="medium",
            category="functional",
            description="d",
            expected="e",
            actual="a",
            suggested_fix="s",
        )
        first = await start_fixing_review_issue(db, scenario["company"].id, issue_id=issue["id"])
        assert first["status"] == "fixing"

        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await start_fixing_review_issue(db, scenario["company"].id, issue_id=issue["id"])
