"""Phase 2 组织 RPC 方法测试（命名空间 org.*）。"""

from __future__ import annotations

from pathlib import Path

import pytest

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
    res = await methods._company_create({"name": "测试公司"})
    return res["company_id"]


async def _make_dept(
    methods: OrganizationMethods, company_id: str, name: str, parent: str = ""
) -> str:
    res = await methods._department_create(
        {"company_id": company_id, "name": name, "parent_department_id": parent}
    )
    return res["department_id"]


async def test_department_move_and_closure(methods: OrganizationMethods) -> None:
    company_id = await _make_company(methods)
    a = await _make_dept(methods, company_id, "A")
    b = await _make_dept(methods, company_id, "B", a)
    d = await _make_dept(methods, company_id, "D")
    res = await methods._department_move({"department_id": b, "new_parent_id": d})
    assert res["moved"] is True
    import aiosqlite

    conn = await aiosqlite.connect(methods._db_path)
    conn.row_factory = aiosqlite.Row
    try:
        cur = await conn.execute(
            "SELECT 1 FROM department_closure WHERE ancestor_department_id = ? AND descendant_department_id = ? AND depth > 0",
            (d, b),
        )
        assert await cur.fetchone() is not None
        cur = await conn.execute(
            "SELECT 1 FROM department_closure WHERE ancestor_department_id = ? AND descendant_department_id = ? AND depth > 0",
            (a, b),
        )
        assert await cur.fetchone() is None
    finally:
        await conn.close()


async def test_department_move_cycle_rejected(methods: OrganizationMethods) -> None:
    company_id = await _make_company(methods)
    a = await _make_dept(methods, company_id, "A")
    b = await _make_dept(methods, company_id, "B", a)
    res = await methods._department_move({"department_id": a, "new_parent_id": b})
    assert "ORG-DEPT-CYCLE" in res["error"]


async def test_department_freeze_unfreeze_archive(methods: OrganizationMethods) -> None:
    company_id = await _make_company(methods)
    dept = await _make_dept(methods, company_id, "X")
    assert (await methods._department_freeze({"department_id": dept}))["status"] == "frozen"
    assert (await methods._department_unfreeze({"department_id": dept}))["status"] == "active"
    assert (await methods._department_archive({"department_id": dept}))["status"] == "archived"


async def test_department_set_leader(methods: OrganizationMethods) -> None:
    company_id = await _make_company(methods)
    dept = await _make_dept(methods, company_id, "X")
    emp = await methods._employee_create(
        {"name": "领导", "company_id": company_id, "department_id": dept}
    )
    res = await methods._department_set_leader(
        {"department_id": dept, "leader_employee_id": emp["employee_id"]}
    )
    assert res["ok"] is True
    assert res["leader_employee_id"] == emp["employee_id"]


async def test_org_graph_get(methods: OrganizationMethods) -> None:
    company_id = await _make_company(methods)
    await _make_dept(methods, company_id, "X")
    await methods._employee_create({"name": "员工", "company_id": company_id})
    res = await methods._org_graph_get({"company_id": company_id})
    assert res["company_id"] == company_id
    assert len(res["departments"]) >= 2
    assert len(res["employees"]) >= 1


async def test_company_activate_and_dissolve(methods: OrganizationMethods) -> None:
    company_id = await _make_company(methods)
    assert (await methods._company_get({"company_id": company_id}))["status"] == "initializing"
    activated = await methods._company_activate(
        {
            "company_id": company_id,
            "expected_version": 1,
            "leader": {"name": "owner", "template_id": "tmpl-bootstrap"},
        }
    )
    assert activated["status"] == "active"
    assert activated["leader_employee_id"]
    dissolved = await methods._company_dissolve(
        {"company_id": company_id, "expected_version": 2, "reason": "test"}
    )
    assert dissolved["status"] == "dissolving"


async def test_department_get_with_closure(methods: OrganizationMethods) -> None:
    company_id = await _make_company(methods)
    a = await _make_dept(methods, company_id, "A")
    b = await _make_dept(methods, company_id, "B", a)
    res = await methods._department_get({"department_id": a})
    assert res["department_id"] == a
    assert b in res["descendants"]
    assert "ancestors" in res


async def test_employee_get_and_set_manager_cycle(methods: OrganizationMethods) -> None:
    company_id = await _make_company(methods)
    dept = await _make_dept(methods, company_id, "X")
    emp = await methods._employee_create(
        {"name": "员工", "company_id": company_id, "department_id": dept}
    )
    eid = emp["employee_id"]
    res = await methods._employee_get({"employee_id": eid})
    assert res["employee_id"] == eid
    # 自环检测
    cyc = await methods._employee_set_manager(
        {"employee_id": eid, "reports_to_employee_id": eid}
    )
    assert "ORG-REPORTING-CYCLE" in cyc["error"]
