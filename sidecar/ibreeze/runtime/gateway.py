"""Agent Run gateway — the main entry point for starting, cancelling, and resuming agent runs.

I.1 四个入口：start / cancel / resume / get_status
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class RunValidationError(ValueError):
    pass


class RunNotFoundError(ValueError):
    pass


async def start(
    db: Any,
    *,
    company_id: str,
    company_task_id: str,
    employee_id: str,
    model_id: str,
    prompt: str,
    run_purpose: str,
    adapter_type: str,
    conversation_id: str,
    availability_snapshot_id: str,
    execution_snapshot_id: str,
    work_item_id: str | None = None,
    department_task_id: str | None = None,
    employee_task_id: str | None = None,
) -> dict[str, Any]:
    """创建唯一的快照绑定 Run，并原子写入事件、Outbox 和队列。

    Gateway 是所有 Run 创建路径的唯一实现。调用方不能只提供任务 ID，
    也不能用请求中的模型或适配器覆盖 ExecutionSnapshot 的不可变绑定。
    """
    required = {
        "company_id": company_id,
        "employee_id": employee_id,
        "company_task_id": company_task_id,
        "conversation_id": conversation_id,
        "availability_snapshot_id": availability_snapshot_id,
        "execution_snapshot_id": execution_snapshot_id,
        "model_id": model_id,
        "run_purpose": run_purpose,
        "adapter_type": adapter_type,
    }
    if any(not str(value or "").strip() for value in required.values()):
        raise RunValidationError("RUNTIME_EXECUTION_SNAPSHOT_REQUIRED")

    valid_purposes = {
        "interactive_turn",
        "company_plan",
        "task_execution",
        "review",
        "verification",
        "repair",
        "merge",
        "summary",
    }
    valid_adapters = {"codex_cli", "claude_code", "opencode", "api_model"}
    if run_purpose not in valid_purposes:
        raise RunValidationError("RUN_PURPOSE_INVALID")
    if adapter_type not in valid_adapters:
        raise RunValidationError("ADAPTER_TYPE_INVALID")

    task_cursor = await db.execute(
        "SELECT id FROM company_tasks WHERE id=? AND company_id=?",
        (company_task_id, company_id),
    )
    if await task_cursor.fetchone() is None:
        raise RunNotFoundError(f"CompanyTask {company_task_id} not found")
    employee_cursor = await db.execute(
        "SELECT id FROM employees WHERE id=? AND company_id=? AND status='active'",
        (employee_id, company_id),
    )
    if await employee_cursor.fetchone() is None:
        raise RunValidationError("EMPLOYEE_UNAVAILABLE")
    conversation_cursor = await db.execute(
        "SELECT id FROM conversations WHERE id=? AND company_id=? AND status='active'",
        (conversation_id, company_id),
    )
    if await conversation_cursor.fetchone() is None:
        raise RunNotFoundError(f"Conversation {conversation_id} not found")

    availability_cursor = await db.execute(
        """SELECT employee_id, company_task_id, department_task_id,
                  work_item_type, work_item_id, overall_status, expires_at
           FROM employee_availability_snapshots
           WHERE id=? AND company_id=?""",
        (availability_snapshot_id, company_id),
    )
    availability = await availability_cursor.fetchone()
    if availability is None or (
        availability["employee_id"] != employee_id
        or availability["company_task_id"] != company_task_id
        or availability["overall_status"] != "available"
        or (
            department_task_id is not None
            and availability["department_task_id"] != department_task_id
        )
    ):
        raise RunValidationError("AVAILABILITY_SNAPSHOT_INVALID")
    try:
        expires_at = datetime.fromisoformat(str(availability["expires_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise RunValidationError("AVAILABILITY_SNAPSHOT_INVALID") from exc
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise RunValidationError("AVAILABILITY_SNAPSHOT_EXPIRED")

    execution_cursor = await db.execute(
        """SELECT company_task_id, department_task_id, employee_task_id,
                  employee_id, snapshot_purpose, work_item_id,
                  runtime_binding_json
           FROM execution_snapshots
           WHERE id=? AND company_id=?""",
        (execution_snapshot_id, company_id),
    )
    execution = await execution_cursor.fetchone()
    if execution is None or (
        execution["company_task_id"] != company_task_id
        or execution["employee_id"] != employee_id
        or (
            department_task_id is not None
            and execution["department_task_id"] != department_task_id
        )
    ):
        raise RunValidationError("EXECUTION_SNAPSHOT_INVALID")
    effective_department_task_id = department_task_id or execution["department_task_id"]
    try:
        binding = json.loads(execution["runtime_binding_json"] or "{}")
    except (TypeError, ValueError) as exc:
        raise RunValidationError("EXECUTION_SNAPSHOT_INVALID") from exc
    if not isinstance(binding, dict):
        raise RunValidationError("EXECUTION_SNAPSHOT_INVALID")
    expected_model_id = str(
        binding.get("api_model")
        or binding.get("model")
        or binding.get("agent_cli")
        or binding.get("agent_key")
        or ""
    )
    expected_adapter_type = str(binding.get("adapter_type") or "")
    if not expected_adapter_type:
        expected_adapter_type = (
            "api_model"
            if binding.get("api_model") or binding.get("model")
            else {
                "codex_cli": "codex_cli",
                "claude_code": "claude_code",
                "opencode": "opencode",
            }.get(str(binding.get("agent_cli") or binding.get("agent_key") or ""), "")
        )
    if expected_adapter_type != adapter_type or expected_model_id != model_id:
        raise RunValidationError("EXECUTION_SNAPSHOT_BINDING_MISMATCH")

    snapshot_employee_task_id = execution["employee_task_id"]
    if employee_task_id is not None and employee_task_id != snapshot_employee_task_id:
        raise RunValidationError("EXECUTION_SNAPSHOT_INVALID")
    effective_employee_task_id = snapshot_employee_task_id
    if run_purpose == "task_execution" and not effective_employee_task_id:
        raise RunValidationError("EMPLOYEE_TASK_REQUIRED")
    if effective_employee_task_id:
        employee_task_cursor = await db.execute(
            """SELECT id FROM employee_tasks
               WHERE id=? AND company_id=? AND employee_id=?""",
            (effective_employee_task_id, company_id, employee_id),
        )
        if await employee_task_cursor.fetchone() is None:
            raise RunValidationError("EMPLOYEE_TASK_SCOPE_MISMATCH")

    expected_availability_type = "task_execution" if run_purpose == "task_execution" else run_purpose
    if availability["work_item_type"] != expected_availability_type:
        raise RunValidationError("AVAILABILITY_SNAPSHOT_INVALID")
    if execution["snapshot_purpose"] != run_purpose:
        raise RunValidationError("EXECUTION_SNAPSHOT_INVALID")

    if run_purpose in {"task_execution", "merge"}:
        if not effective_department_task_id or not effective_employee_task_id:
            raise RunValidationError("EXECUTION_SNAPSHOT_INVALID")
        if run_purpose == "merge":
            merge_cursor = await db.execute(
                "SELECT task_kind FROM employee_tasks WHERE id=? AND company_id=?",
                (effective_employee_task_id, company_id),
            )
            merge_row = await merge_cursor.fetchone()
            if merge_row is None or merge_row["task_kind"] != "merge":
                raise RunValidationError("MERGE_TASK_REQUIRED")
        effective_work_item = effective_employee_task_id
    elif run_purpose in {"company_plan", "summary"}:
        if effective_department_task_id or effective_employee_task_id:
            raise RunValidationError("RUN_SCOPE_MISMATCH")
        effective_work_item = company_task_id
    elif run_purpose == "interactive_turn":
        if effective_department_task_id or effective_employee_task_id:
            raise RunValidationError("RUN_SCOPE_MISMATCH")
        effective_work_item = conversation_id
    else:
        if not work_item_id:
            raise RunValidationError("WORK_ITEM_REQUIRED")
        effective_work_item = str(work_item_id)
        table_by_purpose = {
            "review": "review_assignments",
            "verification": "artifacts",
            "repair": "review_issues",
        }
        work_item_table = table_by_purpose[run_purpose]
        if work_item_table == "review_assignments":
            work_item_cursor = await db.execute(
                """SELECT ra.id, ra.reviewer_employee_id, a.company_task_id
                   FROM review_assignments ra
                   JOIN artifacts a ON a.id=ra.artifact_id AND a.company_id=ra.company_id
                   WHERE ra.id=? AND ra.company_id=?""",
                (effective_work_item, company_id),
            )
        elif work_item_table == "artifacts":
            work_item_cursor = await db.execute(
                "SELECT id, company_task_id FROM artifacts WHERE id=? AND company_id=?",
                (effective_work_item, company_id),
            )
        else:
            work_item_cursor = await db.execute(
                """SELECT ri.id, a.company_task_id
                   FROM review_issues ri
                   JOIN review_reports rr
                     ON rr.id=ri.review_report_id AND rr.company_id=ri.company_id
                   JOIN review_assignments ra
                     ON ra.id=rr.assignment_id AND ra.company_id=rr.company_id
                   JOIN artifacts a
                     ON a.id=ra.artifact_id AND a.company_id=ra.company_id
                   WHERE ri.id=? AND ri.company_id=?""",
                (effective_work_item, company_id),
            )
        work_item_row = await work_item_cursor.fetchone()
        if work_item_row is None:
            raise RunValidationError("WORK_ITEM_NOT_FOUND")
        if work_item_row["company_task_id"] != company_task_id:
            raise RunValidationError("WORK_ITEM_SCOPE_MISMATCH")
        if run_purpose == "review" and work_item_row["reviewer_employee_id"] != employee_id:
            raise RunValidationError("REVIEWER_SCOPE_MISMATCH")

    if work_item_id is not None and str(work_item_id) != effective_work_item:
        raise RunValidationError("WORK_ITEM_SCOPE_MISMATCH")
    if availability["work_item_id"] != effective_work_item or execution["work_item_id"] != effective_work_item:
        raise RunValidationError("EXECUTION_SNAPSHOT_INVALID")
    now = _now()
    run_id = _id()
    spec = {
        "prompt": prompt,
        "model_id": model_id,
        "run_purpose": run_purpose,
        "adapter_type": adapter_type,
        "company_task_id": company_task_id,
        "conversation_id": conversation_id,
        "availability_snapshot_id": availability_snapshot_id,
        "execution_snapshot_id": execution_snapshot_id,
        "work_item_id": effective_work_item,
    }
    spec_json = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    spec_sha256 = hashlib.sha256(spec_json.encode()).hexdigest()
    await db.execute(
        """INSERT INTO agent_runs
           (id, company_id, company_task_id, department_task_id,
            employee_task_id, work_item_id, employee_id, conversation_id,
            availability_snapshot_id, execution_snapshot_id, run_purpose,
            adapter_type, native_session_id, process_pid, process_group_id,
            process_started_at, run_spec_json, run_spec_sha256, status,
            resume_state, attempt, started_at, completed_at, exit_code,
            failure_code, created_at, updated_at, version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,?,?,
                   'queued',NULL,1,NULL,NULL,NULL,NULL,?,?,1)""",
        (
            run_id,
            company_id,
            company_task_id,
            effective_department_task_id,
            effective_employee_task_id,
            effective_work_item,
            employee_id,
            conversation_id,
            availability_snapshot_id,
            execution_snapshot_id,
            run_purpose,
            adapter_type,
            spec_json,
            spec_sha256,
            now,
            now,
        ),
    )
    await db.execute(
        """INSERT INTO runtime_queue
           (id, company_id, work_item_type, work_item_id, job_id, run_id,
            priority, status, queued_at)
           VALUES (?,?,?,?,?,?,?,'ready',?)""",
        (
            _id(),
            company_id,
            "employee_task" if run_purpose == "task_execution" else run_purpose,
            effective_work_item,
            _id(),
            run_id,
            0 if run_purpose in {"interactive_turn", "company_plan", "summary"}
            else 10 if run_purpose in {"task_execution", "repair", "merge"}
            else 20,
            now,
        ),
    )

    trace_id = _id()
    event_id = _id()
    payload = {
        "company_id": company_id,
        "aggregate_id": run_id,
        "version": 1,
        "from_state": "new",
        "to_state": "queued",
    }
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    await db.execute(
        """INSERT INTO agent_run_events
           (event_id, run_id, event_type, payload_json, sequence, trace_id, occurred_at)
           VALUES (?,?,?,?,1,?,?)""",
        (event_id, run_id, "run.queued", payload_json, trace_id, now),
    )
    await db.execute(
        """INSERT INTO domain_events
           (event_id, company_id, aggregate_type, aggregate_id,
            aggregate_version, event_type, payload_json, trace_id, occurred_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (event_id, company_id, "agent_run", run_id, 1, "run.queued", payload_json, trace_id, now),
    )
    await db.execute(
        """INSERT INTO outbox_events
           (id, domain_event_id, topic, payload_json, status, attempts,
            next_attempt_at, created_at)
           VALUES (?,?,?,?,'pending',0,?,?)""",
        (_id(), event_id, "run.queued", payload_json, now, now),
    )
    return {"run_id": run_id, "status": "queued", "created_at": now}


async def cancel(
    db: Any,
    company_id: str,
    run_id: str,
    *,
    reason: str = "",
) -> dict[str, Any]:
    """Cancel through the canonical runtime service and Rust Supervisor."""
    from ibreeze.runtime.service import cancel_run

    result = await cancel_run(db, company_id, run_id)
    result["reason"] = reason
    return result


async def resume(
    db: Any,
    company_id: str,
    run_id: str,
) -> dict[str, Any]:
    """Resume through the canonical queued execution path."""
    from ibreeze.runtime.service import resume_run

    result = await resume_run(db, company_id, run_id)
    result["resumed_at"] = _now()
    return result


async def get_status(
    db: Any,
    company_id: str,
    run_id: str,
) -> dict[str, Any]:
    """Get current status of an agent run."""
    cursor = await db.execute(
        "SELECT * FROM agent_runs WHERE id = ? AND company_id = ?",
        (run_id, company_id),
    )
    run = await cursor.fetchone()
    if not run:
        raise RunNotFoundError(f"Run {run_id} not found")
    return dict(run)
