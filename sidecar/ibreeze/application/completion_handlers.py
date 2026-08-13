from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from typing import Any, cast
from uuid import UUID, uuid4

from ibreeze.domain.tasks.commands import (
    AcceptEmployeeTask,
    CompleteCompanyTask,
    CompleteDepartmentTask,
    StartEmployeeTask,
    SubmitEmployeeTask,
)
from ibreeze.persistence.types import DomainEventRecord, OutboxRecord
from ibreeze.persistence.unit_of_work import CommandResult
from ibreeze.routing.outcomes import RouteOutcomeProjector


def _hash(obj: Any) -> str:
    raw = json.dumps(
        asdict(cast(Any, obj)) if is_dataclass(obj) else obj,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _event(
    event_type: str, aggregate_type: str, task_id: UUID, company_id: UUID, version: int, from_state: str, to_state: str
) -> DomainEventRecord:
    payload = {
        "company_id": str(company_id),
        "aggregate_id": str(task_id),
        "version": version,
        "from_state": from_state,
        "to_state": to_state,
    }
    return DomainEventRecord(
        event_id=uuid4(),
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=task_id,
        aggregate_version=version,
        company_id=company_id,
        payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
        trace_id=str(uuid4()),
    )


def _outbox(topic: str, payload: dict[str, Any], event: DomainEventRecord) -> OutboxRecord:
    return OutboxRecord(topic=topic, payload_json=event.payload_json, domain_event_id=event.event_id)


async def _project_task_outcome(
    session: Any,
    *,
    company_id: UUID,
    task_id: UUID,
    task_column: str,
) -> None:
    if task_column not in {"company_task_id", "department_task_id"}:
        raise ValueError("ROUTE_OUTCOME_TASK_SCOPE_INVALID")
    cursor = await session.execute(
        f"""SELECT rd.id FROM route_decisions rd
            JOIN agent_runs ar ON ar.id=rd.run_id AND ar.company_id=rd.company_id
            WHERE rd.company_id=? AND ar.{task_column}=?
            ORDER BY rd.turn_index DESC, rd.id DESC LIMIT 1""",
        (str(company_id), str(task_id)),
    )
    row = await cursor.fetchone()
    if row is None:
        return
    decision_id = row["id"] if hasattr(row, "keys") else row[0]
    await RouteOutcomeProjector().append(
        session,
        route_decision_id=str(decision_id),
        company_id=str(company_id),
        outcome_type="task_terminal",
        source_id=str(task_id),
        event="task_succeeded",
    )


class EmployeeGate:
    async def blockers(self, session: Any, task_id: UUID, company_id: UUID) -> tuple[str, ...]:
        result: list[str] = []
        if await self._missing_required_artifact(session, task_id, company_id):
            result.append("missing_required_artifact")
        if await self._employee_not_contributor(session, task_id, company_id):
            result.append("employee_not_contributor")
        if await self._verification_not_passed(session, task_id, company_id):
            result.append("verification_not_passed")
        if await self._review_not_submitted(session, task_id, company_id):
            result.append("review_not_submitted")
        if await self._review_not_passed(session, task_id, company_id):
            result.append("review_not_passed")
        if await self._blocking_issue_open(session, task_id, company_id):
            result.append("blocking_issue_open")
        if await self._execution_report_missing(session, task_id, company_id):
            result.append("execution_report_missing")
        if await self._active_run_or_approval(session, task_id, company_id):
            result.append("active_run_or_approval")
        return tuple(result)

    async def _missing_required_artifact(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM employee_tasks et
               JOIN department_tasks dt ON dt.id=et.department_task_id AND dt.company_id=et.company_id
               JOIN artifacts a ON a.company_task_id=dt.company_task_id AND a.company_id=dt.company_id
               WHERE et.id=? AND et.company_id=?
               AND a.is_current=1
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is None

    async def _employee_not_contributor(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM employee_tasks et
               JOIN department_tasks dt ON dt.id=et.department_task_id AND dt.company_id=et.company_id
               WHERE et.id=? AND et.company_id=?
               AND NOT EXISTS (
                   SELECT 1 FROM artifact_contributors ac
                   JOIN artifacts a ON a.id=ac.artifact_id
                   WHERE ac.employee_id=et.employee_id
                   AND a.company_id=et.company_id
                   AND a.company_task_id=dt.company_task_id
                   AND a.is_current=1
               )""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _verification_not_passed(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM employee_tasks et
               JOIN department_tasks dt ON dt.id=et.department_task_id AND dt.company_id=et.company_id
               JOIN artifacts a ON a.company_task_id=dt.company_task_id AND a.company_id=dt.company_id
               WHERE et.id=? AND et.company_id=?
               AND a.is_current=1
               AND NOT EXISTS (
                   SELECT 1 FROM verifications v
                   WHERE v.artifact_id=a.id
                   AND v.company_id=a.company_id
                   AND v.status='passed'
               )
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _review_not_submitted(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM review_assignments ra
               JOIN artifacts a ON a.id=ra.artifact_id
               JOIN department_tasks dt ON dt.company_task_id=a.company_task_id AND dt.company_id=a.company_id
               JOIN employee_tasks et ON et.department_task_id=dt.id AND et.company_id=dt.company_id
               WHERE et.id=? AND et.company_id=?
               AND a.is_current=1
               AND ra.reviewed_sha256=a.object_sha256
               AND ra.status NOT IN ('submitted', 'stale', 'cancelled')
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _review_not_passed(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM review_reports rr
               JOIN review_assignments ra ON ra.id=rr.assignment_id
               JOIN artifacts a ON a.id=ra.artifact_id
               JOIN department_tasks dt ON dt.company_task_id=a.company_task_id AND dt.company_id=a.company_id
               JOIN employee_tasks et ON et.department_task_id=dt.id AND et.company_id=dt.company_id
               WHERE et.id=? AND et.company_id=?
               AND a.is_current=1
               AND ra.status NOT IN ('stale', 'cancelled')
               AND rr.reviewed_sha256=a.object_sha256
               AND rr.verdict!='pass'
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _blocking_issue_open(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM review_issues ri
               JOIN review_reports rr ON rr.id=ri.review_report_id
               JOIN review_assignments ra ON ra.id=rr.assignment_id
               JOIN artifacts a ON a.id=ra.artifact_id
               JOIN department_tasks dt ON dt.company_task_id=a.company_task_id AND dt.company_id=a.company_id
               JOIN employee_tasks et ON et.department_task_id=dt.id AND et.company_id=dt.company_id
               WHERE et.id=? AND et.company_id=?
               AND a.is_current=1
               AND ra.status NOT IN ('stale', 'cancelled')
               AND rr.reviewed_sha256=a.object_sha256
               AND ri.severity IN ('blocker','high')
               AND ri.status NOT IN ('closed', 'rejected')
               AND ri.superseded_by_artifact_id IS NULL
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _execution_report_missing(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM employee_tasks et
               JOIN department_tasks dt ON dt.id=et.department_task_id AND dt.company_id=et.company_id
               LEFT JOIN artifacts a ON a.company_task_id=dt.company_task_id AND a.company_id=dt.company_id
                   AND a.artifact_type='execution_report' AND a.is_current=1
               WHERE et.id=? AND et.company_id=?
               AND a.id IS NULL
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _active_run_or_approval(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM employee_tasks et
               JOIN department_tasks dt ON dt.id=et.department_task_id AND dt.company_id=et.company_id
               LEFT JOIN agent_runs ar ON ar.employee_task_id=et.id
                   AND ar.company_id=et.company_id
                   AND ar.status IN ('queued','running')
               WHERE et.id=? AND et.company_id=?
               AND (
                   ar.id IS NOT NULL
                   OR EXISTS (
                       SELECT 1 FROM agent_runs ar2
                       JOIN human_approvals ha ON ha.run_id=ar2.id
                           AND ha.company_id=ar2.company_id
                       WHERE ar2.employee_task_id=et.id
                         AND ar2.company_id=et.company_id
                         AND ha.status IN ('pending','allowed')
                   )
               )
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None


class DepartmentGate:
    async def blockers(self, session: Any, task_id: UUID, company_id: UUID) -> tuple[str, ...]:
        result: list[str] = []
        if await self._required_employee_tasks_not_accepted(session, task_id, company_id):
            result.append("required_employee_tasks_not_accepted")
        if await self._merge_task_not_accepted(session, task_id, company_id):
            result.append("merge_task_not_accepted")
        if await self._department_report_missing(session, task_id, company_id):
            result.append("department_report_missing")
        if await self._department_review_not_passed(session, task_id, company_id):
            result.append("department_review_not_passed")
        if await self._blocking_issues_open(session, task_id, company_id):
            result.append("blocking_issues_open")
        if await self._verification_not_passed(session, task_id, company_id):
            result.append("verification_not_passed")
        if await self._downstream_deliverables_not_published(session, task_id, company_id):
            result.append("downstream_deliverables_not_published")
        if await self._active_run_or_approval(session, task_id, company_id):
            result.append("active_run_or_approval")
        return tuple(result)

    async def _required_employee_tasks_not_accepted(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM employee_tasks
               WHERE department_task_id=? AND company_id=?
               AND status NOT IN ('accepted', 'cancelled')
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _merge_task_not_accepted(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM employee_tasks
               WHERE department_task_id=? AND company_id=?
               AND task_kind='merge'
               AND status!='accepted'
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _department_report_missing(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM department_tasks dt
               LEFT JOIN artifacts a ON a.company_task_id=dt.company_task_id
                   AND a.artifact_type='department_report' AND a.is_current=1
               WHERE dt.id=? AND dt.company_id=?
               AND a.id IS NULL
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _department_review_not_passed(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM review_reports rr
               JOIN review_assignments ra ON ra.id=rr.assignment_id
               JOIN artifacts a ON a.id=ra.artifact_id AND a.company_id=ra.company_id
               JOIN department_tasks dt ON dt.company_task_id=a.company_task_id
                   AND dt.company_id=a.company_id
               WHERE dt.id=? AND dt.company_id=?
               AND a.artifact_type='department_report'
               AND a.is_current=1
               AND ra.status NOT IN ('stale', 'cancelled')
               AND rr.reviewed_sha256=a.object_sha256
               AND rr.verdict!='pass'
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _blocking_issues_open(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM review_issues ri
               JOIN review_reports rr ON rr.id=ri.review_report_id
               JOIN review_assignments ra ON ra.id=rr.assignment_id
               JOIN artifacts a ON a.id=ra.artifact_id AND a.company_id=ra.company_id
               JOIN department_tasks dt ON dt.company_task_id=a.company_task_id
                   AND dt.company_id=a.company_id
               WHERE dt.id=? AND dt.company_id=?
               AND a.is_current=1
               AND ra.status NOT IN ('stale', 'cancelled')
               AND rr.reviewed_sha256=a.object_sha256
               AND ri.severity IN ('blocker','high')
               AND ri.status NOT IN ('closed', 'rejected')
               AND ri.superseded_by_artifact_id IS NULL
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _verification_not_passed(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM department_tasks dt
               JOIN artifacts a ON a.company_task_id=dt.company_task_id
               WHERE dt.id=? AND dt.company_id=?
               AND a.company_id=dt.company_id
               AND a.is_current=1
               AND a.artifact_type IN ('test_case','test_result')
               AND NOT EXISTS (
                   SELECT 1 FROM verifications v
                   WHERE v.artifact_id=a.id
                   AND v.company_id=a.company_id
                   AND v.status='passed'
               )
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _downstream_deliverables_not_published(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM department_task_deliverables dtd
               WHERE dtd.department_task_id=? AND dtd.company_id=?
               AND dtd.published_at IS NULL
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _active_run_or_approval(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM department_tasks dt
               LEFT JOIN agent_runs ar ON ar.company_task_id=dt.company_task_id
                   AND ar.company_id=dt.company_id
                   AND ar.status IN ('queued','running')
               WHERE dt.id=? AND dt.company_id=?
               AND (
                   ar.id IS NOT NULL
                   OR EXISTS (
                       SELECT 1 FROM agent_runs ar2
                       JOIN human_approvals ha ON ha.run_id=ar2.id
                           AND ha.company_id=ar2.company_id
                       WHERE ar2.company_task_id=dt.company_task_id
                         AND ar2.company_id=dt.company_id
                         AND ha.status IN ('pending','allowed')
                   )
               )
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None


class CompanyGate:
    async def blockers(self, session: Any, task_id: UUID, company_id: UUID) -> tuple[str, ...]:
        result: list[str] = []
        if await self._required_department_tasks_not_completed(session, task_id, company_id):
            result.append("required_department_tasks_not_completed")
        if await self._department_reviews_not_passed(session, task_id, company_id):
            result.append("department_reviews_not_passed")
        if await self._cross_department_review_not_passed(session, task_id, company_id):
            result.append("cross_department_review_not_passed")
        if await self._blocking_issues_open(session, task_id, company_id):
            result.append("blocking_issues_open")
        if await self._final_report_missing(session, task_id, company_id):
            result.append("final_report_missing")
        if await self._ceo_confirmation_missing(session, task_id, company_id):
            result.append("ceo_confirmation_missing")
        if await self._workspace_not_ready(session, task_id, company_id):
            result.append("workspace_not_ready")
        if await self._active_run_or_approval(session, task_id, company_id):
            result.append("active_run_or_approval")
        return tuple(result)

    async def _required_department_tasks_not_completed(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM department_tasks
               WHERE company_task_id=? AND company_id=?
               AND status NOT IN ('completed', 'cancelled')
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _department_reviews_not_passed(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM review_reports rr
               JOIN review_assignments ra ON ra.id=rr.assignment_id
               JOIN artifacts a ON a.id=ra.artifact_id
               WHERE a.company_task_id=? AND a.company_id=?
               AND a.artifact_type='department_report'
               AND a.is_current=1
               AND ra.status NOT IN ('stale', 'cancelled')
               AND rr.reviewed_sha256=a.object_sha256
               AND rr.verdict!='pass'
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _cross_department_review_not_passed(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM review_reports rr
               JOIN review_assignments ra ON ra.id=rr.assignment_id
               JOIN artifacts a ON a.id=ra.artifact_id
               WHERE a.company_task_id=? AND a.company_id=?
               AND a.artifact_type IN ('consolidated_review','cross_department_review')
               AND a.is_current=1
               AND ra.status NOT IN ('stale', 'cancelled')
               AND rr.reviewed_sha256=a.object_sha256
               AND rr.verdict!='pass'
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _blocking_issues_open(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM review_issues ri
               JOIN review_reports rr ON rr.id=ri.review_report_id
               JOIN review_assignments ra ON ra.id=rr.assignment_id
               JOIN artifacts a ON a.id=ra.artifact_id
               WHERE a.company_task_id=? AND a.company_id=?
               AND a.is_current=1
               AND ra.status NOT IN ('stale', 'cancelled')
               AND rr.reviewed_sha256=a.object_sha256
               AND ri.severity IN ('blocker','high')
               AND ri.status NOT IN ('closed', 'rejected')
               AND ri.superseded_by_artifact_id IS NULL
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _final_report_missing(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM company_tasks ct
               LEFT JOIN artifacts a ON a.company_task_id=ct.id
                   AND a.company_id=ct.company_id
                   AND a.artifact_type='final_report' AND a.is_current=1
               WHERE ct.id=? AND ct.company_id=?
               AND a.id IS NULL
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _ceo_confirmation_missing(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM company_tasks
               WHERE id=? AND company_id=?
               AND ceo_confirmed_at IS NULL
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _workspace_not_ready(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM company_tasks ct
               JOIN task_workspaces w ON w.company_task_id=ct.id AND w.company_id=ct.company_id
               WHERE ct.id=? AND ct.company_id=?
               AND w.status NOT IN ('ready_to_apply','applied','abandoned')
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None

    async def _active_run_or_approval(self, session: Any, task_id: UUID, company_id: UUID) -> bool:
        cursor = await session.execute(
            """SELECT 1 FROM company_tasks ct
               LEFT JOIN agent_runs ar ON ar.company_task_id=ct.id
                   AND ar.company_id=ct.company_id
                   AND ar.status IN ('queued','running')
               WHERE ct.id=? AND ct.company_id=?
               AND (
                   ar.id IS NOT NULL
                   OR EXISTS (
                       SELECT 1 FROM agent_runs ar2
                       JOIN human_approvals ha ON ha.run_id=ar2.id
                           AND ha.company_id=ar2.company_id
                       WHERE ar2.company_task_id=ct.id
                         AND ar2.company_id=ct.company_id
                         AND ha.status IN ('pending','allowed')
                   )
               )
               LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        return await cursor.fetchone() is not None


class AcceptEmployeeTaskHandler:
    def __init__(self, gate: EmployeeGate, uow: Any) -> None:
        self._gate = gate
        self._uow = uow

    async def handle(self, context: Any, request: AcceptEmployeeTask) -> Any:
        async def command(session: Any) -> Any:
            task = await self._lock_task(session, request.task_id, request.company_id)
            blockers = await self._gate.blockers(session, request.task_id, request.company_id)
            if blockers:
                raise ValueError(f"COMPLETION_GATE_BLOCKED:{','.join(blockers)}")
            cursor = await session.execute(
                """UPDATE employee_tasks
                   SET status='accepted', version=version+1
                   WHERE id=? AND company_id=? AND version=?""",
                (str(request.task_id), str(request.company_id), task["version"]),
            )
            if cursor.rowcount != 1:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            event = _event(
                "employee_task.status_changed",
                "employee_task",
                request.task_id,
                request.company_id,
                task["version"] + 1,
                task["status"],
                "accepted",
            )
            payload = {
                "company_id": str(request.company_id),
                "aggregate_id": str(request.task_id),
                "version": task["version"] + 1,
                "from_state": task["status"],
                "to_state": "accepted",
                "task_id": str(request.task_id),
            }
            # The second outbox row advances the sequential-refinement graph:
            # it lets AdvanceEmployeeTaskGraph dispatch dependent segments whose
            # upstream is now accepted, inside the same Outbox transaction.
            graph_payload = {
                "company_id": str(request.company_id),
                "aggregate_id": str(request.task_id),
                "version": task["version"] + 1,
                "to_state": "accepted",
                "task_id": str(request.task_id),
            }
            return CommandResult(
                response={"id": str(request.task_id), "status": "accepted"},
                events=(event,),
                outbox=(
                    _outbox("employee_task.status_changed", payload, event),
                    OutboxRecord(
                        topic="employee_task.graph_advance",
                        payload_json=json.dumps(graph_payload, sort_keys=True, separators=(",", ":")),
                        domain_event_id=event.event_id,
                    ),
                ),
            )

        return await self._uow.execute(context, _hash(request), command)

    async def _lock_task(self, session: Any, task_id: UUID, company_id: UUID) -> dict[str, Any]:
        cursor = await session.execute(
            """SELECT id, status, version FROM employee_tasks
               WHERE id=? AND company_id=? LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        return dict(row)


class StartEmployeeTaskHandler:
    """Move an assigned employee task into execution exactly once."""

    def __init__(self, uow: Any) -> None:
        self._uow = uow

    async def handle(self, context: Any, request: StartEmployeeTask) -> Any:
        async def command(session: Any) -> Any:
            cursor = await session.execute(
                "SELECT id, status, version FROM employee_tasks WHERE id=? AND company_id=? LIMIT 1",
                (str(request.task_id), str(request.company_id)),
            )
            row = await cursor.fetchone()
            if row is None:
                raise ValueError("RESOURCE_NOT_FOUND")
            task = dict(row)
            if task["status"] == "running":
                return CommandResult(response={"id": str(request.task_id), "status": "running"})
            if task["status"] not in {"assigned", "ready"} or int(task["version"]) != request.expected_version:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            next_version = int(task["version"]) + 1
            updated = await session.execute(
                """UPDATE employee_tasks
                   SET status='running', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ'), version=?
                   WHERE id=? AND company_id=? AND status IN ('assigned','ready') AND version=?""",
                (next_version, str(request.task_id), str(request.company_id), int(task["version"])),
            )
            if updated.rowcount != 1:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            event = _event(
                "employee_task.status_changed",
                "employee_task",
                request.task_id,
                request.company_id,
                next_version,
                task["status"],
                "running",
            )
            payload = {
                "company_id": str(request.company_id),
                "aggregate_id": str(request.task_id),
                "version": next_version,
                "from_state": task["status"],
                "to_state": "running",
                "task_id": str(request.task_id),
            }
            return CommandResult(
                response={"id": str(request.task_id), "status": "running"},
                events=(event,),
                outbox=(_outbox("employee_task.status_changed", payload, event),),
            )

        return await self._uow.execute(context, _hash(request), command)


class SubmitEmployeeTaskHandler:
    """Convert a successful Run into an employee submission.

    A Run ending successfully is evidence that the Agent loop ended; it is
    not acceptance of the business task.  This handler is the only component
    allowed to make the first business transition after ``run.completed``.
    Review and acceptance remain separate commands and gates.
    """

    def __init__(self, uow: Any) -> None:
        self._uow = uow

    async def handle(self, context: Any, request: SubmitEmployeeTask) -> Any:
        async def command(session: Any) -> Any:
            cursor = await session.execute(
                """SELECT id, status, version FROM employee_tasks
                   WHERE id=? AND company_id=? LIMIT 1""",
                (str(request.task_id), str(request.company_id)),
            )
            row = await cursor.fetchone()
            if row is None:
                raise ValueError("RESOURCE_NOT_FOUND")
            task = dict(row)
            current = task["status"]
            if current in {"submitted", "peer_reviewing", "accepted"}:
                return CommandResult(
                    response={"id": str(request.task_id), "status": current},
                    events=(),
                    outbox=(),
                )
            if current != "running" or int(task["version"]) != request.expected_version:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            updated_version = int(task["version"]) + 1
            updated = await session.execute(
                """UPDATE employee_tasks
                   SET status='submitted', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ'),
                       version=?
                   WHERE id=? AND company_id=? AND status='running' AND version=?""",
                (
                    updated_version,
                    str(request.task_id),
                    str(request.company_id),
                    int(task["version"]),
                ),
            )
            if updated.rowcount != 1:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            event = _event(
                "employee_task.status_changed",
                "employee_task",
                request.task_id,
                request.company_id,
                updated_version,
                "running",
                "submitted",
            )
            payload = {
                "company_id": str(request.company_id),
                "aggregate_id": str(request.task_id),
                "version": updated_version,
                "from_state": "running",
                "to_state": "submitted",
                "task_id": str(request.task_id),
                "run_id": str(request.run_id),
            }
            return CommandResult(
                response={"id": str(request.task_id), "status": "submitted"},
                events=(event,),
                outbox=(_outbox("employee_task.status_changed", payload, event),),
            )

        return await self._uow.execute(context, _hash(request), command)


class CompleteDepartmentTaskHandler:
    def __init__(self, gate: DepartmentGate, uow: Any) -> None:
        self._gate = gate
        self._uow = uow

    async def handle(self, context: Any, request: CompleteDepartmentTask) -> Any:
        async def command(session: Any) -> Any:
            task = await self._lock_task(session, request.task_id, request.company_id)
            blockers = await self._gate.blockers(session, request.task_id, request.company_id)
            if blockers:
                raise ValueError(f"COMPLETION_GATE_BLOCKED:{','.join(blockers)}")
            cursor = await session.execute(
                """UPDATE department_tasks
                   SET status='completed', version=version+1
                   WHERE id=? AND company_id=? AND version=?""",
                (str(request.task_id), str(request.company_id), task["version"]),
            )
            if cursor.rowcount != 1:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            await _project_task_outcome(
                session,
                company_id=request.company_id,
                task_id=request.task_id,
                task_column="department_task_id",
            )
            event = _event(
                "department_task.status_changed",
                "department_task",
                request.task_id,
                request.company_id,
                task["version"] + 1,
                task["status"],
                "completed",
            )
            payload = {
                "company_id": str(request.company_id),
                "aggregate_id": str(request.task_id),
                "version": task["version"] + 1,
                "from_state": task["status"],
                "to_state": "completed",
                "task_id": str(request.task_id),
            }
            return CommandResult(
                response={"id": str(request.task_id), "status": "completed"},
                events=(event,),
                outbox=(_outbox("department_task.status_changed", payload, event),),
            )

        return await self._uow.execute(context, _hash(request), command)

    async def _lock_task(self, session: Any, task_id: UUID, company_id: UUID) -> dict[str, Any]:
        cursor = await session.execute(
            """SELECT id, status, version, company_task_id FROM department_tasks
               WHERE id=? AND company_id=? LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        return dict(row)


class CompleteCompanyTaskHandler:
    def __init__(self, gate: CompanyGate, uow: Any) -> None:
        self._gate = gate
        self._uow = uow

    async def handle(self, context: Any, request: CompleteCompanyTask) -> Any:
        async def command(session: Any) -> Any:
            task = await self._lock_task(session, request.task_id, request.company_id)
            blockers = await self._gate.blockers(session, request.task_id, request.company_id)
            if blockers:
                raise ValueError(f"COMPLETION_GATE_BLOCKED:{','.join(blockers)}")
            cursor = await session.execute(
                """UPDATE company_tasks
                   SET status='completed', version=version+1
                   WHERE id=? AND company_id=? AND version=?""",
                (str(request.task_id), str(request.company_id), task["version"]),
            )
            if cursor.rowcount != 1:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
            await _project_task_outcome(
                session,
                company_id=request.company_id,
                task_id=request.task_id,
                task_column="company_task_id",
            )
            event = _event(
                "company_task.status_changed",
                "company_task",
                request.task_id,
                request.company_id,
                task["version"] + 1,
                task["status"],
                "completed",
            )
            return CommandResult(
                response={"id": str(request.task_id), "status": "completed"},
                events=(event,),
                outbox=(
                    _outbox(
                        "company_task.status_changed",
                        {
                            "company_id": str(request.company_id),
                            "aggregate_id": str(request.task_id),
                            "version": task["version"] + 1,
                            "from_state": task["status"],
                            "to_state": "completed",
                            "task_id": str(request.task_id),
                        },
                        event,
                    ),
                ),
            )

        return await self._uow.execute(context, _hash(request), command)

    async def _lock_task(self, session: Any, task_id: UUID, company_id: UUID) -> dict[str, Any]:
        cursor = await session.execute(
            """SELECT id, status, version FROM company_tasks
               WHERE id=? AND company_id=? LIMIT 1""",
            (str(task_id), str(company_id)),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        return dict(row)
