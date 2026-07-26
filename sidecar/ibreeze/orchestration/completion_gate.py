"""CompletionGate — evidence-backed task completion state machine.

Run exit codes only end runs, not business tasks.
Task completion is gated by actual evidence (artifacts, reviews, test results).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CompletionBlocker:
    code: str
    detail: str


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    blockers: tuple[CompletionBlocker, ...] = ()


class CompletionGate:

    @staticmethod
    async def evaluate_employee_task(
        db: Any,
        task_id: str,
        company_id: str,
    ) -> GateResult:
        blockers: list[CompletionBlocker] = []

        task_row = await (await db.execute(
            """SELECT et.id, et.department_task_id, et.task_kind, et.employee_id, et.status
               FROM employee_tasks et WHERE et.id=? AND et.company_id=?""",
            (task_id, company_id),
        )).fetchone()
        if task_row is None:
            return GateResult(allowed=False, blockers=(
                CompletionBlocker("TASK_NOT_FOUND", "Employee task not found"),
            ))
        task = dict(task_row)

        dt_row = await (await db.execute(
            """SELECT company_task_id FROM department_tasks
               WHERE id=? AND company_id=?""",
            (task["department_task_id"], company_id),
        )).fetchone()
        company_task_id = dict(dt_row)["company_task_id"] if dt_row else task["department_task_id"]

        artifacts = await (await db.execute(
            """SELECT a.id, a.artifact_type, a.object_sha256, a.supersedes_artifact_id
               FROM artifacts a
               WHERE a.company_id=? AND a.company_task_id=?""",
            (company_id, company_task_id),
        )).fetchall()
        task_artifacts = [dict(r) for r in artifacts]

        if not task_artifacts:
            blockers.append(
                CompletionBlocker("MISSING_ARTIFACT", "No artifacts found for this employee task")
            )

        has_contributors = False
        for art in task_artifacts:
            contrib = await (await db.execute(
                """SELECT 1 FROM artifact_contributors
                   WHERE artifact_id=? AND company_id=?""",
                (art["id"], company_id),
            )).fetchone()
            if contrib is not None:
                has_contributors = True
                break
        if not has_contributors:
            blockers.append(
                CompletionBlocker("MISSING_CONTRIBUTORS", "No contributors assigned to any artifact")
            )

        for art in task_artifacts:
            assignments = await (await db.execute(
                """SELECT ra.id, ra.status, ra.reviewed_sha256
                   FROM review_assignments ra
                   WHERE ra.artifact_id=? AND ra.company_id=?
                   ORDER BY ra.review_round DESC, ra.assigned_at DESC
                   LIMIT 1""",
                (art["id"], company_id),
            )).fetchall()
            for row in assignments:
                assign = dict(row)
                if assign["status"] in ("assigned", "in_review"):
                    blockers.append(
                        CompletionBlocker("REVIEW_NOT_SUBMITTED",
                                          f"Review assignment {assign['id']} not yet submitted")
                    )
                elif assign["status"] == "submitted":
                    reports = await (await db.execute(
                        """SELECT rr.id FROM review_reports rr
                           WHERE rr.assignment_id=?""",
                        (assign["id"],),
                    )).fetchall()
                    for rr in reports:
                        rr_id = dict(rr)["id"]
                        open_issues = await (await db.execute(
                            """SELECT ri.id, ri.severity, ri.status FROM review_issues ri
                               WHERE ri.review_report_id=? AND ri.company_id=?
                               AND ri.severity IN ('blocker','high')
                               AND ri.status NOT IN ('closed','rejected','verified')""",
                            (rr_id, company_id),
                        )).fetchall()
                        for iss in open_issues:
                            issue = dict(iss)
                            msg = f"Issue {issue['id']} ({issue['severity']}) is still {issue['status']}"
                            blockers.append(
                                CompletionBlocker("OPEN_BLOCKER_ISSUES", msg)
                            )

        has_previous_review = await (await db.execute(
            """SELECT 1 FROM review_assignments ra
               JOIN review_reports rr ON rr.assignment_id = ra.id
               WHERE ra.artifact_id IN (
                   SELECT id FROM artifacts WHERE company_id=? AND company_task_id=?
               ) AND ra.company_id=?
               AND ra.review_round > 0
               LIMIT 1""",
            (company_id, company_task_id, company_id),
        )).fetchone()

        if has_previous_review is not None:
            superseding = await (await db.execute(
                """SELECT a.id, a.supersedes_artifact_id
                   FROM artifacts a
                   WHERE a.company_id=? AND a.company_task_id=?
                   AND a.supersedes_artifact_id IS NOT NULL
                   ORDER BY a.created_at DESC LIMIT 1""",
                (company_id, company_task_id),
            )).fetchone()
            if superseding is None:
                blockers.append(
                    CompletionBlocker("REWORK_MISSING_VERSION",
                                      "Rework round detected but no new artifact version found")
                )

        if blockers:
            return GateResult(allowed=False, blockers=tuple(blockers))
        return GateResult(allowed=True)

    @staticmethod
    async def evaluate_department_task(
        db: Any,
        task_id: str,
        company_id: str,
    ) -> GateResult:
        blockers: list[CompletionBlocker] = []

        pending_emp = await (await db.execute(
            """SELECT COUNT(*) as cnt FROM employee_tasks
               WHERE department_task_id=? AND company_id=?
               AND status NOT IN ('accepted','cancelled')""",
            (task_id, company_id),
        )).fetchone()
        if pending_emp and pending_emp["cnt"] > 0:
            blockers.append(
                CompletionBlocker("EMPLOYEE_TASKS_NOT_DONE",
                                  f"{pending_emp['cnt']} employee task(s) not yet completed")
            )

        failed_emp = await (await db.execute(
            """SELECT COUNT(*) as cnt FROM employee_tasks
               WHERE department_task_id=? AND company_id=? AND status='failed'""",
            (task_id, company_id),
        )).fetchone()
        if failed_emp and failed_emp["cnt"] > 0:
            blockers.append(
                CompletionBlocker("EMPLOYEE_TASKS_FAILED",
                                  f"{failed_emp['cnt']} employee task(s) in failed state")
            )

        dept_reports = await (await db.execute(
            """SELECT id FROM artifacts
               WHERE company_id=? AND company_task_id IN (
                   SELECT company_task_id FROM department_tasks WHERE id=? AND company_id=?
               ) AND artifact_type='department_report'""",
            (company_id, task_id, company_id),
        )).fetchall()
        if not dept_reports:
            blockers.append(
                CompletionBlocker("MISSING_DEPARTMENT_REPORT",
                                  "Department-level review report not found")
            )

        dept_row = await (await db.execute(
            """SELECT department_id FROM department_tasks WHERE id=? AND company_id=?""",
            (task_id, company_id),
        )).fetchone()
        if dept_row:
            test_cases = await (await db.execute(
                """SELECT 1 FROM artifacts
                   WHERE company_id=? AND artifact_type='test_case'
                   AND department_task_id=?
                   LIMIT 1""",
                (company_id, task_id),
            )).fetchone()
            if test_cases is not None:
                test_results = await (await db.execute(
                    """SELECT 1 FROM artifacts
                       WHERE company_id=? AND artifact_type='test_result'
                       AND department_task_id=?
                       LIMIT 1""",
                    (company_id, task_id),
                )).fetchone()
                if test_results is None:
                    blockers.append(
                        CompletionBlocker("MISSING_TEST_RESULTS",
                                          "Test cases found but no test results")
                    )

        if blockers:
            return GateResult(allowed=False, blockers=tuple(blockers))
        return GateResult(allowed=True)

    @staticmethod
    async def evaluate_company_task(
        db: Any,
        task_id: str,
        company_id: str,
    ) -> GateResult:
        blockers: list[CompletionBlocker] = []

        dept_pending = await (await db.execute(
            """SELECT COUNT(*) as cnt FROM department_tasks
               WHERE company_task_id=? AND company_id=?
               AND status NOT IN ('completed','cancelled')""",
            (task_id, company_id),
        )).fetchone()
        if dept_pending and dept_pending["cnt"] > 0:
            blockers.append(
                CompletionBlocker("DEPARTMENT_TASKS_NOT_DONE",
                                  f"{dept_pending['cnt']} department task(s) not yet completed")
            )

        dept_reports = await (await db.execute(
            """SELECT 1 FROM artifacts
               WHERE company_id=? AND company_task_id=? AND artifact_type='department_report'
               LIMIT 1""",
            (company_id, task_id),
        )).fetchone()
        if dept_reports is None:
            blockers.append(
                CompletionBlocker("MISSING_DEPARTMENT_REPORT",
                                  "No department report found for this company task")
            )

        comp_review = await (await db.execute(
            """SELECT 1 FROM artifacts
               WHERE company_id=? AND company_task_id=? AND artifact_type='review_report'
               LIMIT 1""",
            (company_id, task_id),
        )).fetchone()
        if comp_review is None:
            blockers.append(
                CompletionBlocker("COMPANY_REVIEW_NOT_PASSED",
                                  "Company-level review has not passed")
            )

        final_reports = await (await db.execute(
            """SELECT 1 FROM artifacts
               WHERE company_id=? AND company_task_id=? AND artifact_type='final_report'
               LIMIT 1""",
            (company_id, task_id),
        )).fetchone()
        if final_reports is None:
            blockers.append(
                CompletionBlocker("MISSING_FINAL_REPORT",
                                  "Final company report not generated")
            )

        if blockers:
            return GateResult(allowed=False, blockers=tuple(blockers))
        return GateResult(allowed=True)
