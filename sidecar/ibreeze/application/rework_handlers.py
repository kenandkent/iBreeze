from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from ibreeze.persistence.unit_of_work import CommandResult


def _hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class RequestReworkHandler:
    def __init__(self, uow: Any) -> None:
        self._uow = uow

    async def handle(
        self,
        context: Any,
        request: Any,
    ) -> Any:
        async def command(session: Any) -> Any:
            if not request.source_review_issue_ids:
                raise ValueError("REWORK_REQUIRES_AT_LEAST_ONE_ISSUE")

            for issue_id in request.source_review_issue_ids:
                cursor = await session.execute(
                    """SELECT 1 FROM review_issues
                       WHERE id=? AND company_id=?
                       AND status NOT IN ('closed','rejected')""",
                    (str(issue_id), str(request.company_id)),
                )
                if await cursor.fetchone() is None:
                    raise ValueError(f"ISSUE_NOT_OPEN:{issue_id}")

            dept_id = str(request.department_task_id) if hasattr(request, "department_task_id") and request.department_task_id else ""
            cursor = await session.execute(
                """SELECT COALESCE(MAX(attempt_no), 0) + 1
                   FROM rework_attempts
                   WHERE company_id=? AND company_task_id=?
                   AND COALESCE(department_task_id, '')=?""",
                (str(request.company_id), str(request.company_task_id), dept_id),
            )
            row = await cursor.fetchone()
            next_no = row[0] if row else 1

            attempt_id = str(hashlib.md5(f"{request.company_id}:{request.company_task_id}:{next_no}".encode()).hexdigest()[:32])

            dept_id_val = str(request.department_task_id) if hasattr(request, "department_task_id") and request.department_task_id else None
            await session.execute(
                """INSERT INTO rework_attempts
                   (id, company_id, company_task_id, department_task_id,
                    attempt_no, status, version, created_at)
                   VALUES (?,?,?,?,?,?,1,datetime('now'))""",
                (attempt_id, str(request.company_id), str(request.company_task_id), dept_id_val, next_no, "planned"),
            )

            for issue_id in request.source_review_issue_ids:
                await session.execute(
                    """INSERT INTO rework_attempt_issues
                       (company_id, rework_attempt_id, review_issue_id)
                       VALUES (?,?,?)""",
                    (str(request.company_id), attempt_id, str(issue_id)),
                )

            is_dept = hasattr(request, "department_task_id") and request.department_task_id
            task_type = "department_task" if is_dept else "company_task"
            task_id = request.department_task_id if is_dept else request.company_task_id

            cursor = await session.execute(
                f"""UPDATE {task_type}s
                    SET status='fixing', version=version+1
                    WHERE id=? AND company_id=? AND version=?""",
                (str(task_id), str(request.company_id), request.expected_version),
            )
            if cursor.rowcount != 1:
                raise ValueError("OPTIMISTIC_LOCK_CONFLICT")

            return CommandResult(
                response={
                    "attempt_id": attempt_id,
                    "attempt_no": next_no,
                    "status": "planned",
                },
                events=(
                    {
                        "event_type": f"{task_type}.status_changed",
                        "aggregate_id": str(task_id),
                        "to_state": "fixing",
                    },
                ),
                outbox=(),
            )

        return await self._uow.execute(context, _hash(request), command)


class AdvanceReworkAttemptHandler:
    def __init__(self, uow: Any) -> None:
        self._uow = uow

    async def handle(
        self,
        context: Any,
        attempt_id: UUID,
        company_id: UUID,
        target_status: str,
    ) -> Any:
        allowed_transitions = {
            "planned": frozenset({"running", "cancelled"}),
            "running": frozenset({"completed", "cancelled", "failed"}),
        }

        async def command(session: Any) -> Any:
            cursor = await session.execute(
                """SELECT id, company_task_id, department_task_id, attempt_no,
                          status, version
                   FROM rework_attempts
                   WHERE id=? AND company_id=?""",
                (str(attempt_id), str(company_id)),
            )
            row = await cursor.fetchone()
            if row is None:
                raise ValueError("RESOURCE_NOT_FOUND")
            current_status = row["status"]
            allowed = allowed_transitions.get(current_status, frozenset())
            if target_status not in allowed:
                raise ValueError("STATE_TRANSITION_INVALID")

            if target_status in ("completed", "cancelled", "failed"):
                await session.execute(
                    """UPDATE rework_attempts
                       SET status=?, version=version+1, completed_at=datetime('now')
                       WHERE id=? AND company_id=? AND version=?""",
                    (target_status, str(attempt_id), str(company_id), row["version"]),
                )
            else:
                await session.execute(
                    """UPDATE rework_attempts
                       SET status=?, version=version+1
                       WHERE id=? AND company_id=? AND version=?""",
                    (target_status, str(attempt_id), str(company_id), row["version"]),
                )

            return CommandResult(
                response={
                    "attempt_id": str(attempt_id),
                    "status": target_status,
                },
                events=(),
                outbox=(),
            )

        return await self._uow.execute(context, _hash(locals()), command)
