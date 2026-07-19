"""Phase 4 权限引擎真实集成测试。

覆盖设计 §8.1–§8.4 的核心断言：
- 普通职员仅可见自己部门
- 部门负责人可见本部门 + 后代
- 公司负责人可见全公司部门
- 同部门平级不可见对方 employee_private（核心安全红线）
- 汇报链下属可见性
- 有效 / 过期 access_grant 影响可见部门
- authorize 写 acl_audit_log
"""

from __future__ import annotations

import aiosqlite
from datetime import datetime, timezone
from pathlib import Path

import pytest

from acos.organization.employee_service import EmployeeService
from acos.organization.permission_engine import PermissionEngine
from acos.organization.service import OrganizationService
from acos.organization.template_service import TemplateService
from acos.store.migrator import Migrator


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _insert_department(db_path, company_id, department_id, parent_id, leader=None):
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """INSERT INTO departments
               (department_id, company_id, parent_department_id, name, status, version, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'active', 1, ?, ?)""",
            (department_id, company_id, parent_id, department_id, _now_iso(), _now_iso()),
        )
        # 闭包：自身
        await db.execute(
            "INSERT INTO department_closure (company_id, ancestor_department_id, descendant_department_id, depth) VALUES (?, ?, ?, 0)",
            (company_id, department_id, department_id),
        )
        if parent_id:
            # 复制父链的祖先
            cur = await db.execute(
                "SELECT ancestor_department_id, depth FROM department_closure WHERE company_id = ? AND descendant_department_id = ?",
                (company_id, parent_id),
            )
            for r in await cur.fetchall():
                await db.execute(
                    "INSERT INTO department_closure (company_id, ancestor_department_id, descendant_department_id, depth) VALUES (?, ?, ?, ?)",
                    (company_id, r["ancestor_department_id"], department_id, r["depth"] + 1),
                )
        if leader is not None:
            await db.execute(
                "UPDATE departments SET leader_employee_id = ? WHERE department_id = ?",
                (leader, department_id),
            )
        await db.commit()


async def _set_employee_type(db_path, employee_id, employee_type):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE employees SET employee_type = ? WHERE employee_id = ?",
            (employee_type, employee_id),
        )
        await db.commit()


async def _set_reports_to(db_path, employee_id, manager_id):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE employees SET reports_to_employee_id = ? WHERE employee_id = ?",
            (manager_id, employee_id),
        )
        await db.commit()


async def _set_dept_leader(db_path, department_id, leader_id):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE departments SET leader_employee_id = ? WHERE department_id = ?",
            (leader_id, department_id),
        )
        await db.commit()


async def _set_employee_type_direct(db_path, employee_id, employee_type):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE employees SET employee_type = ? WHERE employee_id = ?",
            (employee_type, employee_id),
        )
        await db.commit()


@pytest.fixture
async def setup(tmp_path: Path):
    db_path = tmp_path / "test.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(str(Path(__file__).resolve().parents[2] / "migrations"))
    org_svc = OrganizationService(str(db_path))
    company = await org_svc.create_company("测试公司", "owner-1")
    await org_svc.activate_company(company.company_id, expected_version=1)
    template_svc = TemplateService(str(db_path))
    template = await template_svc.create(
        company_id=company.company_id, capability_id="cap-001",
        capability_version=1, default_role="开发者",
    )
    await template_svc.activate(template.template_id, company.company_id, expected_version=1)
    emp_svc = EmployeeService(str(db_path))
    engine = PermissionEngine(str(db_path))
    return engine, emp_svc, company.company_id, template.template_id, str(db_path)


async def _make_emp(emp_svc, company_id, template_id, dept, name):
    emp = await emp_svc.create(
        company_id=company_id, department_id=dept, template_id=template_id, name=name,
    )
    return emp.employee_id


async def test_employee_visible_department_only_own(setup):
    engine, emp_svc, company_id, template_id, _ = setup
    dp = emp_svc._db_path
    await _insert_department(dp, company_id, "X", None)
    await _insert_department(dp, company_id, "Y", "X")
    emp = await _make_emp(emp_svc, company_id, template_id, "X", "A")
    scope = await engine.compute_scope(emp, company_id)
    assert scope["visible_department_ids"] == ["X"]
    assert scope["managed_department_ids"] == []


async def test_dept_leader_sees_subtree(setup):
    engine, emp_svc, company_id, template_id, _ = setup
    dp = emp_svc._db_path
    leader = await _make_emp(emp_svc, company_id, template_id, "X", "L")
    await _set_employee_type_direct(dp, leader, "department_leader")
    await _insert_department(dp, company_id, "X", None, leader)
    await _insert_department(dp, company_id, "Y", "X", leader)
    await _insert_department(dp, company_id, "Z", "Y", leader)
    scope = await engine.compute_scope(leader, company_id)
    assert set(scope["managed_department_ids"]) == {"X", "Y", "Z"}
    assert set(scope["visible_department_ids"]) == {"X", "Y", "Z"}


async def test_company_leader_sees_all_departments(setup):
    engine, emp_svc, company_id, template_id, _ = setup
    dp = emp_svc._db_path
    async with aiosqlite.connect(dp) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT root_department_id FROM companies WHERE company_id = ?", (company_id,))
        root = (await cur.fetchone())["root_department_id"]
    await _insert_department(dp, company_id, "X", None)
    await _insert_department(dp, company_id, "Y", "X")
    await _insert_department(dp, company_id, "W", None)
    leader = await _make_emp(emp_svc, company_id, template_id, "X", "CL")
    await _set_employee_type_direct(dp, leader, "company_leader")
    scope = await engine.compute_scope(leader, company_id)
    assert set(scope["visible_department_ids"]) == {root, "X", "Y", "W"}


async def test_peers_cannot_see_each_other_private(setup):
    engine, emp_svc, company_id, template_id, _ = setup
    dp = emp_svc._db_path
    await _insert_department(dp, company_id, "X", None)
    a = await _make_emp(emp_svc, company_id, template_id, "X", "A")
    b = await _make_emp(emp_svc, company_id, template_id, "X", "B")
    scope_b = await engine.compute_scope(b, company_id)
    assert a not in scope_b["private_visible_employee_ids"]
    assert scope_b["employee_id"] == b


async def test_reporting_chain_visibility(setup):
    engine, emp_svc, company_id, template_id, _ = setup
    dp = emp_svc._db_path
    await _insert_department(dp, company_id, "X", None)
    # 平行组长组
    await _insert_department(dp, company_id, "P", None)
    member = await _make_emp(emp_svc, company_id, template_id, "X", "组员")
    lead = await _make_emp(emp_svc, company_id, template_id, "X", "组长")
    head = await _make_emp(emp_svc, company_id, template_id, "X", "部门负责人")
    lead2 = await _make_emp(emp_svc, company_id, template_id, "P", "平行组长")
    await _set_employee_type_direct(dp, head, "department_leader")
    await _set_reports_to(dp, member, lead)
    await _set_reports_to(dp, lead, head)
    # 部门负责人领导 X 部门（含后代）
    await _set_dept_leader(dp, "X", head)

    scope_lead = await engine.compute_scope(lead, company_id)
    assert member in scope_lead["private_visible_employee_ids"]

    scope_head = await engine.compute_scope(head, company_id)
    assert member in scope_head["private_visible_employee_ids"]

    scope_lead2 = await engine.compute_scope(lead2, company_id)
    assert member not in scope_lead2["private_visible_employee_ids"]


async def test_active_grant_adds_department_expired_does_not(setup):
    engine, emp_svc, company_id, template_id, db_path = setup
    await _insert_department(db_path, company_id, "X", None)
    await _insert_department(db_path, company_id, "Y", None)
    emp = await _make_emp(emp_svc, company_id, template_id, "X", "A")

    # 过期授权
    await engine.grant(
        company_id=company_id, employee_id=emp, target_type="department",
        target_id="Y", permission="department_read",
        expires_at="2020-01-01T00:00:00Z", approved_by="system",
    )
    scope = await engine.compute_scope(emp, company_id)
    assert "Y" not in scope["visible_department_ids"]

    # 有效授权
    gid = await engine.grant(
        company_id=company_id, employee_id=emp, target_type="department",
        target_id="Y", permission="department_read",
        expires_at="2099-01-01T00:00:00Z", approved_by="system",
    )
    scope = await engine.compute_scope(emp, company_id)
    assert "Y" in scope["visible_department_ids"]

    # 撤销后立即失效
    await engine.revoke(gid, company_id, expected_version=1)
    scope = await engine.compute_scope(emp, company_id)
    assert "Y" not in scope["visible_department_ids"]


async def test_authorize_writes_audit_log(setup):
    engine, emp_svc, company_id, template_id, db_path = setup
    await _insert_department(db_path, company_id, "X", None)
    await _insert_department(db_path, company_id, "Y", None)
    emp = await _make_emp(emp_svc, company_id, template_id, "X", "A")

    allow = await engine.authorize(emp, company_id, "department", "X")
    assert allow["decision"] == "allow"
    deny = await engine.authorize(emp, company_id, "department", "Y")
    assert deny["decision"] == "deny"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM acl_audit_log WHERE subject = ? ORDER BY timestamp",
            (emp,),
        )
        rows = await cur.fetchall()
    assert len(rows) == 2
    assert rows[0]["decision"] == "allow"
    assert rows[0]["matched_rule"] == "inherited_department"
    assert rows[1]["decision"] == "deny"
    assert rows[1]["matched_rule"] == "default_deny"
