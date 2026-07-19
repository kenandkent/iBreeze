"""test_plan_validator：PV-01..PV-13 参数化（P9-T4 红线）。"""

from __future__ import annotations

import pytest

from acos.task.plan_validator import (
    PlanValidationError,
    PlanValidator,
    ValidationContext,
)
from tests.task.conftest import (
    migrated_db, seed_backend, seed_budget_policy, seed_company_employee,
)


def _ctx(**kw):
    base = dict(
        company_id="co1", manager_employee_id="emp1", manager_scope="company",
        department_id=None, currency="CNY", budget_limit=1_000_000_000,
        est_per_node=1000,
    )
    base.update(kw)
    return ValidationContext(**base)


async def _seed_provider(db, provider_id="p1", model="m1", metered=True, cap=True,
                         frozen=False):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite_helper(db) as db2:
        await db2.execute(
            """INSERT INTO provider_models
               (provider_id, model, billing_mode, enforces_output_cap, owner_company_id)
               VALUES (?, ?, ?, ?, ?)""",
            (provider_id, model, "metered" if metered else "flat",
             int(cap), "co1" if cap else None),
        )
        await db2.commit()


def aiosqlite_helper(db):
    import aiosqlite
    return aiosqlite.connect(db)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", [
    # (dag, ctx_overrides, expect_rule_or_None)
    ("pv01_empty", None, "PV-01"),
    ("pv01_missing_field", None, "PV-01"),
    ("pv01_dup_id", None, "PV-01"),
    ("pv01_bad_type", None, "PV-01"),
    ("pv02_cycle", None, "PV-02"),
    ("pv03_too_deep", None, "PV-03"),
    ("pv04_cross_dept", dict(manager_scope="dept", department_id="depX"), "PV-04"),
    ("pv05_inactive_emp", None, "PV-05"),
    ("pv06_reviewer_same", None, "PV-06"),
    ("pv07_bad_ws", None, "PV-07"),
    ("pv07_manual_write_ws", None, "PV-07"),
    ("pv08_over_budget", dict(budget_limit=10), "PV-08"),
    ("pv09_tool_missing", None, "PV-09"),
    ("pv10_no_schema", None, "PV-10"),
    ("pv10_forbidden_kw", None, "PV-10"),
    ("pv11_bad_provider", None, "PV-11"),
    ("pv12_inactive_dept", None, "PV-12"),
    ("pv13_manual_backend_set", None, "PV-13"),
    ("pv13_bad_backend", None, "PV-13"),
])
async def test_pv_failures(migrated_db, case):
    db = migrated_db
    name, ctx_over, expect = case
    await seed_company_employee(db, employee_id="emp1", capability_snapshot='{"tools":[{"name":"read"}]}')
    await seed_company_employee(db, department_id="depX", leader_employee_id="emp1")
    await seed_company_employee(db, employee_id="emp2")
    await seed_company_employee(db, employee_id="empInactive", status="frozen")
    await seed_company_employee(db, employee_id="emp3", department_id="depBad", dept_status="frozen")
    await seed_backend(db)
    await seed_budget_policy(db)
    await _seed_provider(db)
    dag = _build_dag(name)
    ctx = _ctx(**(ctx_over or {}))
    v = PlanValidator(db)
    with pytest.raises(PlanValidationError) as ei:
        await v.validate(dag, ctx)
    assert ei.value.rule == expect


@pytest.mark.asyncio
@pytest.mark.parametrize("case", [
    ("ok_simple", None),
    ("ok_review_split", None),
    ("ok_manual_no_backend", None),
])
async def test_pv_ok(migrated_db, case):
    db = migrated_db
    name, ctx_over = case
    await seed_company_employee(db, employee_id="emp1", capability_snapshot='{"tools":[{"name":"read"}]}')
    await seed_company_employee(db, employee_id="emp2")
    await seed_backend(db)
    await seed_budget_policy(db)
    dag = _build_dag(name)
    ctx = _ctx(**(ctx_over or {}))
    v = PlanValidator(db)
    res = await v.validate(dag, ctx)
    assert res["ok"]


def _build_dag(name: str) -> list[dict]:
    base_agent = dict(node_id="n1", node_type="agent_step", goal="g",
                      depends_on=[], assignee_employee_id="emp1",
                      workspace_strategy="TaskWorkspace",
                      outputs_schema={"type": "object"}, tools=["read"])
    cases = {
        "pv01_empty": [],
        "pv01_missing_field": [{"node_id": "n1", "node_type": "agent_step"}],
        "pv01_dup_id": [
            {"node_id": "n1", "node_type": "agent_step", "goal": "g"},
            {"node_id": "n1", "node_type": "agent_step", "goal": "g2"},
        ],
        "pv01_bad_type": [{"node_id": "n1", "node_type": "bogus", "goal": "g"}],
        "pv02_cycle": [
            {"node_id": "n1", "node_type": "agent_step", "goal": "g", "depends_on": ["n2"]},
            {"node_id": "n2", "node_type": "agent_step", "goal": "g", "depends_on": ["n1"]},
        ],
        "pv03_too_deep": [
            {"node_id": f"n{i}", "node_type": "agent_step", "goal": "g",
             "depends_on": [f"n{i-1}"] if i > 0 else []}
            for i in range(10)
        ],
        "pv04_cross_dept": [dict(base_agent, assignee_employee_id="emp2")],
        "pv05_inactive_emp": [dict(base_agent, assignee_employee_id="empInactive")],
        "pv06_reviewer_same": [{
            "node_id": "n1", "node_type": "review_task", "goal": "g",
            "depends_on": [], "worker_employee_id": "emp1",
            "reviewer_employee_id": "emp1", "workspace_strategy": "ReadOnly",
            "outputs_schema": {"type": "object"}}],
        "pv07_bad_ws": [dict(base_agent, workspace_strategy="BadWS")],
        "pv07_manual_write_ws": [{
            "node_id": "n1", "node_type": "manual_task", "goal": "g",
            "depends_on": [], "workspace_strategy": "GitWorktree",
            "outputs_schema": {"type": "object"}}],
        "pv08_over_budget": [dict(base_agent)],
        "pv09_tool_missing": [dict(base_agent, tools=["nonexistent_tool"])],
        "pv10_no_schema": [dict(base_agent, outputs_schema=None)],
        "pv10_forbidden_kw": [dict(base_agent, outputs_schema={"$ref": "x"})],
        "pv11_bad_provider": [dict(base_agent, hard_budget=True,
                                   provider_id="bad", model="x")],
        "pv12_inactive_dept": [dict(base_agent, assignee_employee_id="emp3", tools=[])],
        "pv13_manual_backend_set": [{
            "node_id": "n1", "node_type": "manual_task", "goal": "g",
            "depends_on": [], "backend_id": "be1",
            "outputs_schema": {"type": "object"}}],
        "pv13_bad_backend": [dict(base_agent, backend_id="nope")],
        "ok_simple": [dict(base_agent)],
        "ok_review_split": [
            dict(base_agent),
            {"node_id": "n2", "node_type": "review_task", "goal": "r",
             "depends_on": ["n1"], "worker_employee_id": "emp1",
             "reviewer_employee_id": "emp2", "workspace_strategy": "ReadOnly",
             "outputs_schema": {"type": "object"}}],
        "ok_manual_no_backend": [{
            "node_id": "n1", "node_type": "manual_task", "goal": "g",
            "depends_on": [], "workspace_strategy": "ReadOnly",
            "outputs_schema": {"type": "object"}}],
    }
    return cases[name]
