"""企业员工与部门管理领域服务。

提供员工 CRUD（含软删除）、部门 CRUD、角色管理能力。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ibreeze.schemas import (
    DepartmentCreate,
    DepartmentResponse,
    EmployeeCreate,
    EmployeeResponse,
    EmployeeStatus,
    EmployeeUpdate,
)


# ── 内存存储 ──────────────────────────────────────────────────────────────

_employees: dict[str, dict[str, Any]] = {}
_departments: dict[str, dict[str, Any]] = {}


def _now_utc() -> datetime:
    """返回当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ── 员工 CRUD ─────────────────────────────────────────────────────────────

def create_employee(
    company_id: str,
    name: str,
    department_id: str | None = None,
    role: str = "member",
    email: str | None = None,
) -> EmployeeResponse:
    """创建员工。"""
    import uuid

    emp_id = str(uuid.uuid4())
    now = _now_utc()

    record: dict[str, Any] = {
        "id": emp_id,
        "company_id": company_id,
        "name": name,
        "department_id": department_id,
        "role": role,
        "email": email,
        "status": EmployeeStatus.ACTIVE,
        "is_deleted": False,
        "created_at": now,
        "updated_at": now,
    }
    _employees[emp_id] = record
    return EmployeeResponse(**record)


def list_employees(
    company_id: str | None = None,
    department_id: str | None = None,
    role: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> list[EmployeeResponse]:
    """分页列出员工，可按企业、部门、角色过滤。"""
    active = [
        e
        for e in _employees.values()
        if not e["is_deleted"]
        and (company_id is None or e["company_id"] == company_id)
        and (department_id is None or e["department_id"] == department_id)
        and (role is None or e["role"] == role)
    ]
    return [EmployeeResponse(**e) for e in active[offset : offset + limit]]


def get_employee(emp_id: str) -> EmployeeResponse:
    """获取单个员工详情。"""
    record = _employees.get(emp_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"员工不存在: {emp_id}")
    return EmployeeResponse(**record)


def update_employee(emp_id: str, data: EmployeeUpdate) -> EmployeeResponse:
    """更新员工信息（部分更新）。"""
    record = _employees.get(emp_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"员工不存在: {emp_id}")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        record[key] = value
    record["updated_at"] = _now_utc()

    return EmployeeResponse(**record)


def delete_employee(emp_id: str) -> None:
    """软删除员工。"""
    record = _employees.get(emp_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"员工不存在: {emp_id}")
    record["is_deleted"] = True
    record["updated_at"] = _now_utc()


# ── 部门 CRUD ─────────────────────────────────────────────────────────────

def create_department(
    company_id: str,
    name: str,
    parent_id: str | None = None,
) -> DepartmentResponse:
    """创建部门。"""
    import uuid

    dept_id = str(uuid.uuid4())
    now = _now_utc()

    record: dict[str, Any] = {
        "id": dept_id,
        "company_id": company_id,
        "name": name,
        "parent_id": parent_id,
        "is_deleted": False,
        "created_at": now,
        "updated_at": now,
    }
    _departments[dept_id] = record
    return DepartmentResponse(**record)


def list_departments(
    company_id: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[DepartmentResponse]:
    """列出部门。"""
    active = [
        d
        for d in _departments.values()
        if not d["is_deleted"] and (company_id is None or d["company_id"] == company_id)
    ]
    return [DepartmentResponse(**d) for d in active[offset : offset + limit]]


def get_department(dept_id: str) -> DepartmentResponse:
    """获取单个部门详情。"""
    record = _departments.get(dept_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"部门不存在: {dept_id}")
    return DepartmentResponse(**record)
