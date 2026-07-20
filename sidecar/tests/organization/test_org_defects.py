"""组织域 6 处缺陷修复验证（SC 用例）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.organization.employee_service import EmployeeService
from acos.organization.service import OrganizationService
from acos.rpc.methods_org import OrganizationMethods
from acos.store.migrator import Migrator


@pytest.fixture
async def methods(tmp_path: Path) -> OrganizationMethods:
    db_path = str(tmp_path / "test.db")
    migrator = Migrator(db_path)
    await migrator.run_pending_migrations(
        str(Path(__file__).resolve().parents[2] / "migrations")
    )
    return OrganizationMethods(db_path)


async def _make_company(methods: OrganizationMethods) -> str:
    return (await methods._company_create({"name": "测试公司"}))["company_id"]


async def _activate(methods: OrganizationMethods, company_id: str) -> None:
    await methods._company_activate({"company_id": company_id, "expected_version": 1})


async def _make_dept(methods: OrganizationMethods, company_id: str, name: str, parent: str = "") -> str:
    return (await methods._department_create(
        {"company_id": company_id, "name": name, "parent_department_id": parent}
    ))["department_id"]


async def _make_employee(methods: OrganizationMethods, company_id: str, dept: str = "", name: str = "员工") -> str:
    return (await methods._employee_create(
        {"name": name, "company_id": company_id, "department_id": dept}
    ))["employee_id"]


# SC-02-1 冻结部门仍可建子部门
async def test_frozen_dept_reject_subdepartment(methods: OrganizationMethods) -> None:
    company_id = await _make_company(methods)
    parent = await _make_dept(methods, company_id, "父")
    await methods._department_freeze({"department_id": parent})
    res = await methods._department_create(
        {"company_id": company_id, "name": "子", "parent_department_id": parent}
    )
    assert "ORG-DEPT-FROZEN" in res["error"]
    # 解冻后仍可建
    await methods._department_unfreeze({"department_id": parent})
    ok = await methods._department_create(
        {"company_id": company_id, "name": "子2", "parent_department_id": parent}
    )
    assert "department_id" in ok


# SC-02-2 含员工部门删除未拒绝
async def test_dept_with_employees_reject_delete(methods: OrganizationMethods) -> None:
    company_id = await _make_company(methods)
    dept = await _make_dept(methods, company_id, "含员部门")
    await _make_employee(methods, company_id, dept)
    res = await methods._department_delete({"department_id": dept})
    assert "ORG-DEPT-HAS-EMPLOYEES" in res["error"]
    # 空部门仍可软删
    empty = await _make_dept(methods, company_id, "空部门")
    ok = await methods._department_delete({"department_id": empty})
    assert ok.get("deleted") is True


# SC-03-2 跨公司模板串快照
async def test_employee_create_cross_company_template_denied(methods: OrganizationMethods) -> None:
    c1 = await _make_company(methods)
    c2 = await _make_company(methods)
    # 在 c2 下做一个 active 模板
    emp_svc2 = EmployeeService(methods._db_path)
    await _activate(methods, c2)
    tmpl = await emp_svc2.create(company_id=c2, department_id="", template_id="", name="种子")
    # 直接插入一条属于 c2 的 active 模板记录
    import aiosqlite, json
    conn = await aiosqlite.connect(methods._db_path)
    tid = "tmpl-x-" + c2[:8]
    try:
        await conn.execute(
            """INSERT INTO employee_templates
               (template_id, template_scope, company_id, provider_type, provider_id,
                model, capability_id, capability_version, capability_snapshot,
                default_role, version, status)
               VALUES (?, 'company', ?, 'openai', 'openai', 'gpt-4', '', 1, ?, 'r', 1, 'active')""",
            (tid, c2, json.dumps({"cap": 1})),
        )
        await conn.commit()
    finally:
        await conn.close()
    # c1 员工引用 c2 模板 → 拒绝
    res = await methods._employee_create(
        {"name": "E", "company_id": c1, "template_id": tid}
    )
    assert res["error"] == "ORG-TEMPLATE-CROSS-COMPANY-DENIED"


# SC-03-3 setManager 环检测改用员工汇报链
async def test_set_manager_reporting_cycle_via_service(methods: OrganizationMethods) -> None:
    company_id = await _make_company(methods)
    await _activate(methods, company_id)
    a = await _make_employee(methods, company_id, name="A")
    b = await _make_employee(methods, company_id, name="B")
    # A 汇报给 B
    ok = await methods._employee_set_manager(
        {"employee_id": a, "reports_to_employee_id": b, "expected_version": 1}
    )
    assert ok["ok"] is True
    # B 汇报给 A → 应形成环，被员工汇报链闭包检测拒绝
    cyc = await methods._employee_set_manager(
        {"employee_id": b, "reports_to_employee_id": a, "expected_version": 1}
    )
    assert "ORG-REPORTING-CYCLE" in cyc["error"]


# SC-03-4 员工软删 + 状态机 deleted
async def test_employee_soft_delete_and_state_machine(methods: OrganizationMethods) -> None:
    company_id = await _make_company(methods)
    await _activate(methods, company_id)
    eid = await _make_employee(methods, company_id, name="待删")
    # created 状态不允许直接 deleted
    bad = await methods._employee_delete({"employee_id": eid, "expected_version": 1})
    assert "ORG-STATE-INVALID" in bad["error"]
    # 经由服务层：激活 → 归档 → 软删
    svc = EmployeeService(methods._db_path)
    await svc.activate(eid, company_id, expected_version=1)
    await svc.archive(eid, company_id, expected_version=2)
    res = await methods._employee_delete({"employee_id": eid, "expected_version": 3})
    assert res.get("deleted") is True
    assert res.get("status") == "deleted"
    # 软删后不在列表返回
    lst = await methods._employee_list({"company_id": company_id})
    assert all(e["employee_id"] != eid for e in lst)


# SC-21-2 员工建/改绑校验模板 active
async def test_employee_create_inactive_template_denied(methods: OrganizationMethods) -> None:
    company_id = await _make_company(methods)
    await _activate(methods, company_id)
    import aiosqlite, json
    tid = "tmpl-inactive-" + company_id[:8]
    conn = await aiosqlite.connect(methods._db_path)
    try:
        await conn.execute(
            """INSERT INTO employee_templates
               (template_id, template_scope, company_id, provider_type, provider_id,
                model, capability_id, capability_version, capability_snapshot,
                default_role, version, status)
               VALUES (?, 'company', ?, 'openai', 'openai', 'gpt-4', '', 1, ?, 'r', 1, 'draft')""",
            (tid, company_id, json.dumps({})),
        )
        await conn.commit()
    finally:
        await conn.close()
    res = await methods._employee_create(
        {"name": "E", "company_id": company_id, "template_id": tid}
    )
    assert res["error"] == "ORG-TEMPLATE-NOT-ACTIVE"

    # update 改绑非 active 模板同样拒绝
    eid = await _make_employee(methods, company_id, name="改绑")
    upd = await methods._employee_update(
        {"employee_id": eid, "company_id": company_id, "template_id": tid}
    )
    assert upd["error"] == "ORG-TEMPLATE-NOT-ACTIVE"
