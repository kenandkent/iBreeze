"""Transactional Department and Employee aggregate commands."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from ibreeze.company import _normalize_name
from ibreeze.schemas import (
    DepartmentCreate,
    DepartmentResponse,
    DepartmentType,
    DepartmentUpdate,
    EmployeeCreate,
    EmployeeResponse,
    EmployeeStatus,
    EmployeeUpdateDisplay,
    WorkflowRole,
)


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _one(cursor: Any) -> Any | None:
    return await cursor.fetchone()


async def _all(cursor: Any) -> list[Any]:
    return list(await cursor.fetchall())


def _department(row: Any) -> DepartmentResponse:
    return DepartmentResponse(
        id=row["id"],
        company_id=row["company_id"],
        department_type=row["department_type"],
        normalized_name=row["normalized_name"],
        current_revision_id=row["current_revision_id"],
        leader_employee_id=row["leader_employee_id"],
        department_conversation_id=row["department_conversation_id"],
        status=row["status"],
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
        version=row["version"],
    )


def _employee(row: Any) -> EmployeeResponse:
    return EmployeeResponse(
        id=row["id"],
        company_id=row["company_id"],
        department_id=row["department_id"],
        display_name=row["display_name"],
        normalized_display_name=row["normalized_display_name"],
        base_profile_version_id=row["base_profile_version_id"],
        workflow_role=row["workflow_role"],
        status=row["status"],
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
        version=row["version"],
    )


async def _published_profile(db: Any, profile_version_id: str) -> None:
    cursor = await db.execute(
        """SELECT id FROM employee_base_profile_versions
           WHERE id=? AND status='published'""",
        (profile_version_id,),
    )
    if await _one(cursor) is None:
        raise ValueError("PROFILE_VERSION_INVALID")


async def _active_company(db: Any, company_id: str) -> None:
    cursor = await db.execute(
        "SELECT status FROM companies WHERE id=?",
        (company_id,),
    )
    row = await _one(cursor)
    if row is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    if row["status"] != "active":
        raise ValueError("COMPANY_ARCHIVED")


async def _append_event(
    db: Any,
    *,
    company_id: str,
    aggregate_type: str,
    aggregate_id: str,
    aggregate_version: int,
    event_type: str,
    extra: dict[str, object] | None = None,
) -> None:
    now = _now()
    event_id = _id()
    payload = {
        "company_id": company_id,
        "aggregate_id": aggregate_id,
        "aggregate_version": aggregate_version,
        **(extra or {}),
    }
    payload_json = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    await db.execute(
        """INSERT INTO domain_events
           (event_id, company_id, aggregate_type, aggregate_id,
            aggregate_version, event_type, payload_json, trace_id, occurred_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_id,
            company_id,
            aggregate_type,
            aggregate_id,
            aggregate_version,
            event_type,
            payload_json,
            _id(),
            now,
        ),
    )
    await db.execute(
        """INSERT INTO outbox_events
           (id, domain_event_id, topic, payload_json, status, attempts,
            next_attempt_at, created_at)
           VALUES (?, ?, ?, ?, 'pending', 0, ?, ?)""",
        (_id(), event_id, event_type, payload_json, now, now),
    )


async def create_department(
    db: Any,
    company_id: str,
    data: DepartmentCreate,
) -> DepartmentResponse:
    """Atomically create a standard department, leader, revision and conversation."""
    await _active_company(db, company_id)
    await _published_profile(db, data.base_profile_version_id)
    normalized_name = _normalize_name(data.name)
    normalized_leader = _normalize_name(data.leader_name)

    await db.execute("BEGIN IMMEDIATE")
    await db.execute("PRAGMA defer_foreign_keys = ON")
    try:
        cursor = await db.execute(
            "SELECT id FROM departments WHERE company_id=? AND normalized_name=?",
            (company_id, normalized_name),
        )
        if await _one(cursor) is not None:
            raise ValueError("NAME_EXISTS")

        department_id = _id()
        revision_id = _id()
        leader_id = _id()
        conversation_id = _id()
        now = _now()
        await db.execute(
            """INSERT INTO departments
               (id, company_id, department_type, normalized_name,
                current_revision_id, leader_employee_id,
                department_conversation_id, status, created_at, updated_at,
                version)
               VALUES (?, ?, 'standard', ?, ?, ?, ?, 'active', ?, ?, 1)""",
            (
                department_id,
                company_id,
                normalized_name,
                revision_id,
                leader_id,
                conversation_id,
                now,
                now,
            ),
        )
        revision_json = json.dumps(
            {
                "name": data.name,
                "function_description": data.function_description,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        await db.execute(
            """INSERT INTO department_revisions
               (id, department_id, company_id, revision_number, name,
                function_description, content_sha256, created_at)
               VALUES (?, ?, ?, 1, ?, ?, ?, ?)""",
            (
                revision_id,
                department_id,
                company_id,
                data.name,
                data.function_description,
                hashlib.sha256(revision_json.encode()).hexdigest(),
                now,
            ),
        )
        await db.execute(
            """INSERT INTO employees
               (id, company_id, department_id, display_name,
                normalized_display_name, base_profile_version_id,
                workflow_role, status, created_at, updated_at, version)
               VALUES (?, ?, ?, ?, ?, ?, 'department_leader', 'active',
                       ?, ?, 1)""",
            (
                leader_id,
                company_id,
                department_id,
                data.leader_name,
                normalized_leader,
                data.base_profile_version_id,
                now,
                now,
            ),
        )
        await db.execute(
            """INSERT INTO conversations
               (id, company_id, conversation_type, department_id, status,
                created_at)
               VALUES (?, ?, 'department', ?, 'active', ?)""",
            (conversation_id, company_id, department_id, now),
        )
        await _append_event(
            db,
            company_id=company_id,
            aggregate_type="department",
            aggregate_id=department_id,
            aggregate_version=1,
            event_type="department.created",
            extra={"leader_employee_id": leader_id},
        )
        await db.commit()
        return await get_department(db, company_id, department_id)
    except Exception:
        await db.rollback()
        raise
    finally:
        cursor = await db.execute("PRAGMA defer_foreign_keys")
        row = await _one(cursor)
        assert row is not None
        if row[0] != 0:
            await db.execute("PRAGMA defer_foreign_keys = OFF")
            raise RuntimeError("defer_foreign_keys was not restored")


async def get_department(
    db: Any,
    company_id: str,
    department_id: str,
) -> DepartmentResponse:
    cursor = await db.execute(
        "SELECT * FROM departments WHERE id=? AND company_id=?",
        (department_id, company_id),
    )
    row = await _one(cursor)
    if row is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    return _department(row)


async def list_departments(
    db: Any,
    company_id: str,
    *,
    limit: int = 50,
    after: tuple[str, str] | None = None,
) -> list[DepartmentResponse]:
    if after is None:
        cursor = await db.execute(
            """SELECT * FROM departments WHERE company_id=?
               ORDER BY created_at DESC, id DESC LIMIT ?""",
            (company_id, limit),
        )
    else:
        cursor = await db.execute(
            """SELECT * FROM departments WHERE company_id=?
               AND (created_at < ? OR (created_at = ? AND id < ?))
               ORDER BY created_at DESC, id DESC LIMIT ?""",
            (company_id, after[0], after[0], after[1], limit),
        )
    return [_department(row) for row in await _all(cursor)]


async def update_department(
    db: Any,
    company_id: str,
    department_id: str,
    data: DepartmentUpdate,
) -> DepartmentResponse:
    await _active_company(db, company_id)
    await db.execute("BEGIN IMMEDIATE")
    try:
        cursor = await db.execute(
            """SELECT d.*, r.name, r.function_description
               FROM departments d
               JOIN department_revisions r ON r.id=d.current_revision_id
               WHERE d.id=? AND d.company_id=? AND d.version=?""",
            (department_id, company_id, data.expected_version),
        )
        current = await _one(cursor)
        if current is None:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
        if current["status"] != "active":
            raise ValueError("STATE_TRANSITION_INVALID")

        name = data.name or current["name"]
        description = data.function_description or current["function_description"]
        normalized_name = _normalize_name(name)
        cursor = await db.execute(
            """SELECT id FROM departments
               WHERE company_id=? AND normalized_name=? AND id<>?""",
            (company_id, normalized_name, department_id),
        )
        if await _one(cursor) is not None:
            raise ValueError("NAME_EXISTS")

        revision_id = _id()
        now = _now()
        content = json.dumps(
            {"name": name, "function_description": description},
            ensure_ascii=False,
            sort_keys=True,
        )
        await db.execute(
            """INSERT INTO department_revisions
               (id, department_id, company_id, revision_number, name,
                function_description, content_sha256, created_at)
               VALUES (?, ?, ?,
                 (SELECT COALESCE(MAX(revision_number),0)+1
                  FROM department_revisions WHERE department_id=?),
                 ?, ?, ?, ?)""",
            (
                revision_id,
                department_id,
                company_id,
                department_id,
                name,
                description,
                hashlib.sha256(content.encode()).hexdigest(),
                now,
            ),
        )
        version = data.expected_version + 1
        await db.execute(
            """UPDATE departments SET normalized_name=?,
               current_revision_id=?, updated_at=?, version=?
               WHERE id=? AND company_id=? AND version=?""",
            (
                normalized_name,
                revision_id,
                now,
                version,
                department_id,
                company_id,
                data.expected_version,
            ),
        )
        await _append_event(
            db,
            company_id=company_id,
            aggregate_type="department",
            aggregate_id=department_id,
            aggregate_version=version,
            event_type="department.updated",
        )
        await db.commit()
        return await get_department(db, company_id, department_id)
    except Exception:
        await db.rollback()
        raise


async def create_employee(
    db: Any,
    company_id: str,
    department_id: str,
    data: EmployeeCreate,
) -> EmployeeResponse:
    await _active_company(db, company_id)
    await _published_profile(db, data.base_profile_version_id)
    if data.workflow_role != WorkflowRole.MEMBER:
        raise ValueError("STATE_TRANSITION_INVALID")
    normalized_name = _normalize_name(data.display_name)
    await db.execute("BEGIN IMMEDIATE")
    try:
        cursor = await db.execute(
            """SELECT id FROM departments
               WHERE id=? AND company_id=? AND status='active'""",
            (department_id, company_id),
        )
        if await _one(cursor) is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        cursor = await db.execute(
            """SELECT id FROM employees
               WHERE department_id=? AND normalized_display_name=?""",
            (department_id, normalized_name),
        )
        if await _one(cursor) is not None:
            raise ValueError("NAME_EXISTS")
        employee_id = _id()
        now = _now()
        await db.execute(
            """INSERT INTO employees
               (id, company_id, department_id, display_name,
                normalized_display_name, base_profile_version_id,
                workflow_role, status, created_at, updated_at, version)
               VALUES (?, ?, ?, ?, ?, ?, 'member', 'active', ?, ?, 1)""",
            (
                employee_id,
                company_id,
                department_id,
                data.display_name,
                normalized_name,
                data.base_profile_version_id,
                now,
                now,
            ),
        )
        await _append_event(
            db,
            company_id=company_id,
            aggregate_type="employee",
            aggregate_id=employee_id,
            aggregate_version=1,
            event_type="employee.created",
            extra={"department_id": department_id},
        )
        await db.commit()
        return await get_employee(db, company_id, employee_id)
    except Exception:
        await db.rollback()
        raise


async def get_employee(
    db: Any,
    company_id: str,
    employee_id: str,
) -> EmployeeResponse:
    cursor = await db.execute(
        "SELECT * FROM employees WHERE id=? AND company_id=?",
        (employee_id, company_id),
    )
    row = await _one(cursor)
    if row is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    return _employee(row)


async def list_employees(
    db: Any,
    company_id: str,
    *,
    department_id: str | None = None,
    limit: int = 50,
    after: tuple[str, str] | None = None,
) -> list[EmployeeResponse]:
    if department_id is None and after is None:
        cursor = await db.execute(
            """SELECT * FROM employees WHERE company_id=?
               ORDER BY created_at DESC,id DESC LIMIT ?""",
            (company_id, limit),
        )
    elif department_id is None:
        assert after is not None
        cursor = await db.execute(
            """SELECT * FROM employees WHERE company_id=?
               AND (created_at < ? OR (created_at = ? AND id < ?))
               ORDER BY created_at DESC,id DESC LIMIT ?""",
            (company_id, after[0], after[0], after[1], limit),
        )
    elif after is None:
        cursor = await db.execute(
            """SELECT * FROM employees
               WHERE company_id=? AND department_id=?
               ORDER BY created_at DESC,id DESC LIMIT ?""",
            (company_id, department_id, limit),
        )
    else:
        cursor = await db.execute(
            """SELECT * FROM employees
               WHERE company_id=? AND department_id=?
               AND (created_at < ? OR (created_at = ? AND id < ?))
               ORDER BY created_at DESC,id DESC LIMIT ?""",
            (
                company_id,
                department_id,
                after[0],
                after[0],
                after[1],
                limit,
            ),
        )
    return [_employee(row) for row in await _all(cursor)]


async def update_employee_display_name(
    db: Any,
    company_id: str,
    employee_id: str,
    data: EmployeeUpdateDisplay,
) -> EmployeeResponse:
    await _active_company(db, company_id)
    normalized_name = _normalize_name(data.display_name)
    await db.execute("BEGIN IMMEDIATE")
    try:
        cursor = await db.execute(
            """SELECT * FROM employees
               WHERE id=? AND company_id=? AND version=?""",
            (employee_id, company_id, data.expected_version),
        )
        employee = await _one(cursor)
        if employee is None:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
        cursor = await db.execute(
            """SELECT id FROM employees WHERE department_id=?
               AND normalized_display_name=? AND id<>?""",
            (employee["department_id"], normalized_name, employee_id),
        )
        if await _one(cursor) is not None:
            raise ValueError("NAME_EXISTS")
        version = data.expected_version + 1
        await db.execute(
            """UPDATE employees SET display_name=?,
               normalized_display_name=?, updated_at=?, version=?
               WHERE id=? AND company_id=? AND version=?""",
            (
                data.display_name,
                normalized_name,
                _now(),
                version,
                employee_id,
                company_id,
                data.expected_version,
            ),
        )
        await _append_event(
            db,
            company_id=company_id,
            aggregate_type="employee",
            aggregate_id=employee_id,
            aggregate_version=version,
            event_type="employee.updated",
        )
        await db.commit()
        return await get_employee(db, company_id, employee_id)
    except Exception:
        await db.rollback()
        raise


async def update_employee_base_profile(
    db: Any,
    company_id: str,
    employee_id: str,
    profile_version_id: str,
    *,
    expected_version: int,
) -> EmployeeResponse:
    await _active_company(db, company_id)
    await _published_profile(db, profile_version_id)
    cursor = await db.execute(
        """UPDATE employees SET base_profile_version_id=?, updated_at=?,
           version=version+1 WHERE id=? AND company_id=? AND version=?""",
        (
            profile_version_id,
            _now(),
            employee_id,
            company_id,
            expected_version,
        ),
    )
    if cursor.rowcount != 1:
        await db.rollback()
        raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
    await _append_event(
        db,
        company_id=company_id,
        aggregate_type="employee",
        aggregate_id=employee_id,
        aggregate_version=expected_version + 1,
        event_type="employee.updated",
        extra={"base_profile_version_id": profile_version_id},
    )
    await db.commit()
    return await get_employee(db, company_id, employee_id)


async def _has_active_assignment(db: Any, employee_id: str) -> bool:
    cursor = await db.execute(
        """SELECT 1 FROM employee_tasks
           WHERE employee_id=? AND status NOT IN
           ('accepted','cancelled','failed') LIMIT 1""",
        (employee_id,),
    )
    return await _one(cursor) is not None


async def update_employee_status(
    db: Any,
    company_id: str,
    employee_id: str,
    status: EmployeeStatus,
    *,
    expected_version: int,
) -> EmployeeResponse:
    await _active_company(db, company_id)
    employee = await get_employee(db, company_id, employee_id)
    if employee.workflow_role == WorkflowRole.GENERAL_MANAGER:
        raise ValueError("STATE_TRANSITION_INVALID")
    if status in {EmployeeStatus.INACTIVE, EmployeeStatus.UNAVAILABLE} and (
        await _has_active_assignment(db, employee_id)
    ):
        raise ValueError("EMPLOYEE_HAS_ACTIVE_ASSIGNMENT")
    cursor = await db.execute(
        """UPDATE employees SET status=?,updated_at=?,version=version+1
           WHERE id=? AND company_id=? AND version=?""",
        (status.value, _now(), employee_id, company_id, expected_version),
    )
    if cursor.rowcount != 1:
        await db.rollback()
        raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
    await _append_event(
        db,
        company_id=company_id,
        aggregate_type="employee",
        aggregate_id=employee_id,
        aggregate_version=expected_version + 1,
        event_type="employee.status_changed",
        extra={"status": status.value},
    )
    await db.commit()
    return await get_employee(db, company_id, employee_id)


async def set_department_leader(
    db: Any,
    company_id: str,
    department_id: str,
    employee_id: str,
    *,
    expected_version: int,
) -> DepartmentResponse:
    department = await get_department(db, company_id, department_id)
    if department.department_type == DepartmentType.GENERAL_MANAGER_OFFICE:
        raise ValueError("STATE_TRANSITION_INVALID")
    employee = await get_employee(db, company_id, employee_id)
    if employee.department_id != department_id or employee.status != EmployeeStatus.ACTIVE:
        raise ValueError("LEADER_PROFILE_UNAVAILABLE")
    if department.leader_employee_id == employee_id:
        return department

    await db.execute("BEGIN IMMEDIATE")
    try:
        cursor = await db.execute(
            """UPDATE departments SET leader_employee_id=?,updated_at=?,
               version=version+1 WHERE id=? AND company_id=? AND version=?""",
            (
                employee_id,
                _now(),
                department_id,
                company_id,
                expected_version,
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
        await db.execute(
            """UPDATE employees SET workflow_role='member',version=version+1,
               updated_at=? WHERE id=? AND company_id=?""",
            (_now(), department.leader_employee_id, company_id),
        )
        await db.execute(
            """UPDATE employees SET workflow_role='department_leader',
               version=version+1,updated_at=? WHERE id=? AND company_id=?""",
            (_now(), employee_id, company_id),
        )
        await _append_event(
            db,
            company_id=company_id,
            aggregate_type="department",
            aggregate_id=department_id,
            aggregate_version=expected_version + 1,
            event_type="department.leader_changed",
            extra={"leader_employee_id": employee_id},
        )
        await db.commit()
        return await get_department(db, company_id, department_id)
    except Exception:
        await db.rollback()
        raise
