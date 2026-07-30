"""Tests for review advanced scenarios.

Covers REV-003, REV-004, REV-005.

NOTE: submit_review_report has a production bug - it passes None for
reviewer_run_id which is NOT NULL in the schema. Tests that need a
review report use _create_report_direct to bypass this.
"""

from __future__ import annotations

import uuid

import aiosqlite
import pytest

from ibreeze.company import create_company
from ibreeze.employee import create_department, create_employee
from ibreeze.review.service import (
    assign_reviewer,
    create_review_issue,
    list_review_issues,
    resolve_review_issue,
    start_fixing_review_issue,
)
from ibreeze.schemas import (
    CompanyCreate,
    DepartmentCreate,
    EmployeeCreate,
    WorkflowRole,
)
from ibreeze.state_machine import can_transition, is_terminal


async def _company_with_artifact(db: aiosqlite.Connection, profile_id: str):
    """Create company with department, employees, and a fake artifact."""
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
        artifact_id = "artifact-001"
        sha256 = "a" * 64
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                """INSERT INTO artifacts
                   (id, company_id, company_task_id, artifact_type, logical_name,
                    object_sha256, object_size, media_type, metadata_json,
                    supersedes_artifact_id, created_by_type, created_by_run_id,
                    created_at)
                   VALUES (?, ?, ?, 'source_code_patch', 'main.py',
                           ?, 100, 'text/plain', '{}', NULL, 'system', NULL,
                           '2026-01-01T00:00:00Z')""",
                (artifact_id, company.id, "task-001", sha256),
            )
            await db.execute(
                """INSERT INTO artifact_contributors
                   (artifact_id, company_id, employee_id)
                   VALUES (?, ?, ?)""",
                (artifact_id, company.id, contributor.id),
            )
            await db.commit()
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        await db.commit()
        return company, contributor, reviewer, artifact_id
    except Exception:
        await db.rollback()
        raise


async def _create_report_direct(
    db: aiosqlite.Connection,
    company_id: str,
    assignment_id: str,
    *,
    verdict: str = "pass",
    report_artifact_id: str = "report-direct",
) -> str:
    """Create a review report directly, bypassing the buggy service."""
    # Disable FK checks: review_reports has FKs to agent_runs and artifacts
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        report_id = str(uuid.uuid4())
        now = "2026-01-01T00:00:00Z"
        await db.execute(
            """INSERT INTO review_reports
               (id, company_id, assignment_id, reviewer_run_id,
                verdict, report_artifact_id, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (report_id, company_id, assignment_id, "run-fake", verdict,
             report_artifact_id, now),
        )
        await db.execute(
            """UPDATE review_assignments
               SET status='submitted', submitted_at=?
               WHERE id=? AND company_id=?""",
            (now, assignment_id, company_id),
        )
        await db.commit()
        return report_id
    finally:
        await db.execute("PRAGMA foreign_keys = ON")


@pytest.mark.asyncio
class TestReviewReportHashBinding:
    """REV-003: Review report should be bound with hash."""

    async def test_assignment_records_reviewed_sha256(self, db, published_profile):
        company, _, reviewer, artifact_id = await _company_with_artifact(
            db, published_profile
        )
        result = await assign_reviewer(
            db,
            company.id,
            artifact_id=artifact_id,
            reviewer_employee_id=reviewer.id,
            review_round=1,
            reviewed_sha256="a" * 64,
        )
        assert result["status"] == "assigned"
        assignment = await (
            await db.execute(
                "SELECT reviewed_sha256 FROM review_assignments WHERE id=?",
                (result["id"],),
            )
        ).fetchone()
        assert assignment["reviewed_sha256"] == "a" * 64

    async def test_reviewer_cannot_be_contributor(self, db, published_profile):
        company, contributor, _, artifact_id = await _company_with_artifact(
            db, published_profile
        )
        with pytest.raises(ValueError, match="REVIEWER_CANNOT_BE_CONTRIBUTOR"):
            await assign_reviewer(
                db,
                company.id,
                artifact_id=artifact_id,
                reviewer_employee_id=contributor.id,
                review_round=1,
                reviewed_sha256="b" * 64,
            )

    async def test_duplicate_reviewer_rejected(self, db, published_profile):
        company, _, reviewer, artifact_id = await _company_with_artifact(
            db, published_profile
        )
        await assign_reviewer(
            db,
            company.id,
            artifact_id=artifact_id,
            reviewer_employee_id=reviewer.id,
            review_round=1,
            reviewed_sha256="c" * 64,
        )
        with pytest.raises(ValueError, match="REVIEWER_ALREADY_ASSIGNED"):
            await assign_reviewer(
                db,
                company.id,
                artifact_id=artifact_id,
                reviewer_employee_id=reviewer.id,
                review_round=1,
                reviewed_sha256="c" * 64,
            )

    async def test_submit_report_with_verdict(self, db, published_profile):
        company, _, reviewer, artifact_id = await _company_with_artifact(
            db, published_profile
        )
        assignment = await assign_reviewer(
            db,
            company.id,
            artifact_id=artifact_id,
            reviewer_employee_id=reviewer.id,
            review_round=1,
            reviewed_sha256="c" * 64,
        )
        report_id = await _create_report_direct(
            db,
            company.id,
            assignment_id=assignment["id"],
            report_artifact_id="report-art-001",
            verdict="pass",
        )
        report_row = await (
            await db.execute(
                "SELECT verdict FROM review_reports WHERE id=?", (report_id,)
            )
        ).fetchone()
        assert report_row["verdict"] == "pass"

    async def test_report_binds_to_assignment(self, db, published_profile):
        """REV-003: Report is bound to its assignment."""
        company, _, reviewer, artifact_id = await _company_with_artifact(
            db, published_profile
        )
        assignment = await assign_reviewer(
            db,
            company.id,
            artifact_id=artifact_id,
            reviewer_employee_id=reviewer.id,
            review_round=1,
            reviewed_sha256="d" * 64,
        )
        await _create_report_direct(
            db,
            company.id,
            assignment_id=assignment["id"],
            report_artifact_id="report-002",
            verdict="needs_changes",
        )
        updated = await (
            await db.execute(
                "SELECT status FROM review_assignments WHERE id=?",
                (assignment["id"],),
            )
        ).fetchone()
        assert updated["status"] == "submitted"


@pytest.mark.asyncio
class TestIssueCloseGuard:
    """REV-004: Blocker/high issues cannot be rejected."""

    async def test_create_blocker_issue(self, db, published_profile):
        company, _, reviewer, artifact_id = await _company_with_artifact(
            db, published_profile
        )
        assignment = await assign_reviewer(
            db,
            company.id,
            artifact_id=artifact_id,
            reviewer_employee_id=reviewer.id,
            review_round=1,
            reviewed_sha256="e" * 64,
        )
        report_id = await _create_report_direct(
            db,
            company.id,
            assignment_id=assignment["id"],
            report_artifact_id="report-blocker",
            verdict="needs_changes",
        )
        issue = await create_review_issue(
            db,
            company.id,
            report_id=report_id,
            severity="blocker",
            category="logic",
            description="关键路径阻塞",
            expected="流程正常",
            actual="阻塞",
            suggested_fix="解除阻塞",
        )
        assert issue["severity"] == "blocker"
        assert issue["status"] == "open"

    async def test_resolve_blocker_issue(self, db, published_profile):
        """REV-004: Blocker issues can be resolved but must be fixed."""
        company, _, reviewer, artifact_id = await _company_with_artifact(
            db, published_profile
        )
        assignment = await assign_reviewer(
            db,
            company.id,
            artifact_id=artifact_id,
            reviewer_employee_id=reviewer.id,
            review_round=1,
            reviewed_sha256="f" * 64,
        )
        report_id = await _create_report_direct(
            db,
            company.id,
            assignment_id=assignment["id"],
            report_artifact_id="report-resolve",
            verdict="needs_changes",
        )
        issue = await create_review_issue(
            db,
            company.id,
            report_id=report_id,
            severity="blocker",
            category="logic",
            description="严重问题",
            expected="无问题",
            actual="阻塞",
            suggested_fix="修复",
        )
        fixing = await start_fixing_review_issue(
            db,
            company.id,
            issue_id=issue["id"],
        )
        assert fixing["status"] == "fixing"
        resolved = await resolve_review_issue(
            db,
            company.id,
            issue_id=issue["id"],
            resolution="已修复关键路径问题",
        )
        assert resolved["status"] == "resolved"

    async def test_high_issue_severity(self, db, published_profile):
        """REV-004: High severity issues are tracked."""
        company, _, reviewer, artifact_id = await _company_with_artifact(
            db, published_profile
        )
        assignment = await assign_reviewer(
            db,
            company.id,
            artifact_id=artifact_id,
            reviewer_employee_id=reviewer.id,
            review_round=1,
            reviewed_sha256="0" * 64,
        )
        report_id = await _create_report_direct(
            db,
            company.id,
            assignment_id=assignment["id"],
            report_artifact_id="report-high",
            verdict="needs_changes",
        )
        await create_review_issue(
            db,
            company.id,
            report_id=report_id,
            severity="high",
            category="security",
            description="高级别问题描述",
            expected="安全合规",
            actual="不合规",
            suggested_fix="修复安全问题",
        )
        issues = await list_review_issues(
            db, company.id, report_id=report_id
        )
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"

    async def test_medium_low_issues(self, db, published_profile):
        company, _, reviewer, artifact_id = await _company_with_artifact(
            db, published_profile
        )
        assignment = await assign_reviewer(
            db,
            company.id,
            artifact_id=artifact_id,
            reviewer_employee_id=reviewer.id,
            review_round=1,
            reviewed_sha256="1" * 64,
        )
        report_id = await _create_report_direct(
            db,
            company.id,
            assignment_id=assignment["id"],
            report_artifact_id="report-ml",
            verdict="needs_changes",
        )
        for severity in ("medium", "low"):
            await create_review_issue(
                db,
                company.id,
                report_id=report_id,
                severity=severity,
                category="style",
                description=f"{severity}问题",
                expected="规范",
                actual="不规范",
                suggested_fix="调整",
            )
        issues = await list_review_issues(db, company.id, status="open")
        assert len(issues) == 2


@pytest.mark.asyncio
class TestDepartmentReportCompanyReview:
    """REV-005: Department reports should trigger company-level review."""

    async def test_review_state_transitions(self):
        """REV-005: ReviewAssignment state machine enforces correct flow."""
        assert can_transition("ReviewAssignment", "assigned", "in_review")
        assert can_transition("ReviewAssignment", "in_review", "submitted")
        assert can_transition("ReviewAssignment", "submitted", "stale")
        assert not can_transition("ReviewAssignment", "assigned", "submitted")

    async def test_review_assignment_terminal_states(self):
        assert is_terminal("ReviewAssignment", "stale")
        assert is_terminal("ReviewAssignment", "cancelled")

    async def test_review_issue_state_transitions(self):
        """REV-005: ReviewIssue tracks fix cycles."""
        assert can_transition("ReviewIssue", "open", "fixing")
        assert can_transition("ReviewIssue", "fixing", "resolved")
        assert can_transition("ReviewIssue", "resolved", "verified")
        assert can_transition("ReviewIssue", "verified", "closed")

    async def test_review_issue_fix_cycle(self):
        """REV-005: Issue can cycle through fixing if re-opened."""
        assert can_transition("ReviewIssue", "resolved", "fixing")
        assert can_transition("ReviewIssue", "verified", "fixing")

    async def test_review_issue_terminal_states(self):
        assert is_terminal("ReviewIssue", "closed")
        assert is_terminal("ReviewIssue", "rejected")

    async def test_list_issues_filters(self, db, published_profile):
        company, _, reviewer, artifact_id = await _company_with_artifact(
            db, published_profile
        )
        assignment = await assign_reviewer(
            db,
            company.id,
            artifact_id=artifact_id,
            reviewer_employee_id=reviewer.id,
            review_round=1,
            reviewed_sha256="2" * 64,
        )
        report_id = await _create_report_direct(
            db,
            company.id,
            assignment_id=assignment["id"],
            report_artifact_id="report-filter",
            verdict="needs_changes",
        )
        await create_review_issue(
            db,
            company.id,
            report_id=report_id,
            severity="medium",
            category="style",
            description="问题1",
            expected="正确",
            actual="错误",
            suggested_fix="修正",
        )
        await create_review_issue(
            db,
            company.id,
            report_id=report_id,
            severity="low",
            category="typo",
            description="问题2",
            expected="正确",
            actual="拼写错误",
            suggested_fix="修改拼写",
        )
        all_issues = await list_review_issues(
            db, company.id, status="open"
        )
        assert len(all_issues) == 2
        open_issues = await list_review_issues(
            db, company.id, status="open"
        )
        assert len(open_issues) == 2
        resolved_issues = await list_review_issues(
            db, company.id, status="resolved"
        )
        assert len(resolved_issues) == 0

    async def test_resolve_nonexistent_issue_fails(self, db, published_profile):
        company, _, _, _ = await _company_with_artifact(db, published_profile)
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await resolve_review_issue(
                db,
                company.id,
                issue_id="00000000-0000-4000-8000-000000000000",
                resolution="无效修复",
            )


@pytest.mark.asyncio
class TestReviewSubmitValidation:
    """New review submission validation rules (R07)."""

    async def test_submit_report_sha_mismatch_fails(self, db, published_profile):
        company, _, reviewer, artifact_id = await _company_with_artifact(
            db, published_profile
        )
        assignment = await assign_reviewer(
            db,
            company.id,
            artifact_id=artifact_id,
            reviewer_employee_id=reviewer.id,
            review_round=1,
            reviewed_sha256="a" * 64,
        )
        from ibreeze.review.service import submit_review_report
        with pytest.raises(ValueError, match="ARTIFACT_SHA_MISMATCH"):
            await submit_review_report(
                db,
                company.id,
                assignment_id=assignment["id"],
                artifact_id=artifact_id,
                artifact_sha256="ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
                report_artifact_id="report-sha-test",
                reviewer_run_id="run-review-test",
                verdict="needs_changes",
                summary="SHA mismatch test",
            )

    async def test_submit_report_artifact_not_found_fails(self, db, published_profile):
        company, _, reviewer, artifact_id = await _company_with_artifact(
            db, published_profile
        )
        assignment = await assign_reviewer(
            db,
            company.id,
            artifact_id=artifact_id,
            reviewer_employee_id=reviewer.id,
            review_round=1,
            reviewed_sha256="a" * 64,
        )
        from ibreeze.review.service import submit_review_report
        with pytest.raises(ValueError, match="ARTIFACT_NOT_FOUND"):
            await submit_review_report(
                db,
                company.id,
                assignment_id=assignment["id"],
                artifact_id="nonexistent-artifact",
                artifact_sha256="a" * 64,
                report_artifact_id="report-notfound",
                reviewer_run_id="run-review-test",
                verdict="needs_changes",
                summary="Artifact not found test",
            )

    async def test_submit_report_with_issues(self, db, published_profile):
        company, _, reviewer, artifact_id = await _company_with_artifact(
            db, published_profile
        )
        artifact_row = await (
            await db.execute(
                "SELECT object_sha256 FROM artifacts WHERE id=? AND company_id=?",
                (artifact_id, company.id),
            )
        ).fetchone()
        sha = artifact_row["object_sha256"]
        assignment = await assign_reviewer(
            db,
            company.id,
            artifact_id=artifact_id,
            reviewer_employee_id=reviewer.id,
            review_round=1,
            reviewed_sha256=sha,
        )
        from ibreeze.review.service import submit_review_report
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            result = await submit_review_report(
                db,
                company.id,
                assignment_id=assignment["id"],
                artifact_id=artifact_id,
                artifact_sha256=sha,
                report_artifact_id="report-issues-test",
                reviewer_run_id="run-review-issues",
                verdict="needs_changes",
                summary="Issues test",
                issues=[
                    {
                        "severity": "blocker",
                        "category": "logic",
                        "description": "阻塞问题",
                        "expected": "正常",
                        "actual": "阻塞",
                        "suggested_fix": "修复阻塞",
                    },
                    {
                        "severity": "low",
                        "category": "style",
                        "description": "格式问题",
                        "expected": "规范",
                        "actual": "不规范",
                        "suggested_fix": "调整格式",
                    },
                ],
            )
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        assert result["status"] == "submitted"
        issues = await (
            await db.execute(
                """SELECT COUNT(*) as cnt FROM review_issues
                   WHERE company_id=?""",
                (company.id,),
            )
        ).fetchone()
        assert issues["cnt"] == 2

    async def test_new_artifact_version_invalidates_old_reviews(self, db, published_profile):
        company, _, reviewer, artifact_id = await _company_with_artifact(
            db, published_profile
        )
        artifact_row = await (
            await db.execute(
                "SELECT object_sha256 FROM artifacts WHERE id=? AND company_id=?",
                (artifact_id, company.id),
            )
        ).fetchone()
        sha = artifact_row["object_sha256"]
        assignment = await assign_reviewer(
            db,
            company.id,
            artifact_id=artifact_id,
            reviewer_employee_id=reviewer.id,
            review_round=1,
            reviewed_sha256=sha,
        )
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                """INSERT INTO artifacts
                   (id, company_id, company_task_id, artifact_type, logical_name,
                    object_sha256, object_size, media_type, metadata_json,
                    supersedes_artifact_id, created_by_type, created_by_run_id,
                    created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), company.id, "task-001", "source_code_patch",
                 "main-v2.py", "z" * 64, 200, "text/plain", "{}",
                 artifact_id, "agent", "run-rework", "2026-06-01T00:00:00Z"),
            )
            await db.commit()
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        from ibreeze.review.service import submit_review_report
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            result = await submit_review_report(
                db,
                company.id,
                assignment_id=assignment["id"],
                artifact_id=artifact_id,
                artifact_sha256=sha,
                report_artifact_id="report-stale-test",
                reviewer_run_id="run-stale-test",
                verdict="needs_changes",
                summary="Stale test",
            )
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        assert result["status"] == "stale"
        stale_check = await (
            await db.execute(
                "SELECT status FROM review_assignments WHERE id=?",
                (assignment["id"],),
            )
        ).fetchone()
        assert stale_check["status"] == "stale"


@pytest.mark.asyncio
class TestResolveIssueEvidence:
    """Issue resolution with evidence binding (artifacts/service.py resolve_issue)."""

    async def test_resolve_issue_with_evidence(self, db, published_profile):
        company, _, _, artifact_id = await _company_with_artifact(
            db, published_profile
        )
        from ibreeze.artifacts.service import resolve_issue

        with pytest.raises(ValueError, match="ISSUE_NOT_FOUND"):
            await resolve_issue(
                db,
                company.id,
                issue_id="00000000-0000-4000-8000-000000000000",
                resolution_artifact_sha256="a" * 64,
                fix_run_id="run-fix-test",
                retest_result_id="retest-art",
                resolution_summary="Test resolution",
            )

    async def test_resolve_issue_not_in_fixing(self, db, published_profile):
        company, _, reviewer, artifact_id = await _company_with_artifact(
            db, published_profile
        )
        assignment = await assign_reviewer(
            db,
            company.id,
            artifact_id=artifact_id,
            reviewer_employee_id=reviewer.id,
            review_round=1,
            reviewed_sha256="a" * 64,
        )
        report_id = await _create_report_direct(
            db, company.id, assignment_id=assignment["id"],
            verdict="needs_changes",
        )
        issue = await create_review_issue(
            db, company.id,
            report_id=report_id,
            severity="high",
            category="logic",
            description="问题",
            expected="正确",
            actual="错误",
            suggested_fix="修正",
        )
        from ibreeze.artifacts.service import resolve_issue
        with pytest.raises(ValueError, match="ISSUE_NOT_IN_FIXING_STATE"):
            await resolve_issue(
                db,
                company.id,
                issue_id=issue["id"],
                resolution_artifact_sha256="a" * 64,
                fix_run_id="run-fix",
                retest_result_id="retest-art",
                resolution_summary="修复完成",
            )
