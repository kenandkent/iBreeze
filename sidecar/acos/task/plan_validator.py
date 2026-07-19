"""Plan 校验器（P9-T4，PV-01..PV-13）。

执行前强制关卡。任一步失败抛 PlanValidationError（结构化）。
高风险计划创建 plan_approval（接 gov approval）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

import aiosqlite

from acos.governance.service import GovernanceService
from acos.rpc.errors import AcosError

WF_PLAN_INVALID = "WF-PLAN-INVALID"


class PlanValidationError(AcosError):
    def __init__(self, rule: str, message: str, cause: str = "") -> None:
        super().__init__(
            code=WF_PLAN_INVALID,
            message=f"[{rule}] {message}",
            cause=cause,
            suggestion="修正计划后重新校验",
        )
        self.rule = rule


@dataclass
class ValidationContext:
    company_id: str
    manager_employee_id: str
    manager_scope: str
    department_id: Optional[str] = None
    currency: Optional[str] = None
    budget_limit: int = 0
    est_per_node: int = 0
    assignee_departments: dict = field(default_factory=dict)
    assignee_status: dict = field(default_factory=dict)
    assignee_snapshot_tools: dict = field(default_factory=dict)


def detect_cycle(nodes: list[dict]) -> bool:
    """环检测（DAG 必须无环）。"""
    by_id = {n.get("node_id"): n for n in nodes}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in by_id}

    def dfs(nid: str) -> bool:
        color[nid] = GRAY
        node = by_id.get(nid)
        if node:
            for dep in node.get("depends_on", []) or []:
                if dep not in by_id:
                    continue
                if color[dep] == GRAY:
                    return True
                if color[dep] == WHITE and dfs(dep):
                    return True
        color[nid] = BLACK
        return False

    for nid in by_id:
        if color[nid] == WHITE:
            if dfs(nid):
                return True
    return False


def max_depth(nodes: list[dict]) -> int:
    by_id = {n.get("node_id"): n for n in nodes}
    memo: dict[str, int] = {}

    def depth(nid: str) -> int:
        if nid in memo:
            return memo[nid]
        node = by_id.get(nid)
        if not node:
            return 1
        deps = node.get("depends_on", []) or []
        if not deps:
            memo[nid] = 1
            return 1
        d = 1 + max(depth(d) for d in deps if d in by_id)
        memo[nid] = d
        return d

    if not nodes:
        return 0
    return max(depth(n.get("node_id")) for n in nodes)


class PlanValidator:
    """PV-01..PV-13。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._gov = GovernanceService(db_path)

    async def validate(self, dag: list[dict], ctx: ValidationContext) -> dict:
        self._pv01_schema(dag)
        if detect_cycle(dag):
            raise PlanValidationError("PV-02", "DAG 存在环", "depends_on 形成环路")
        await self._pv03_scale(dag, ctx.company_id)
        await self._load_assignees(dag, ctx)
        self._pv04_department_scope(dag, ctx)
        self._pv05_employee_status(dag, ctx)
        self._pv06_reviewer_independence(dag)
        self._pv07_workspace(dag)
        self._pv08_budget_estimate(dag, ctx)
        self._pv09_tool_binding(dag, ctx)
        self._pv10_output_schema(dag)
        await self._pv11_hard_budget_provider(dag, ctx)
        await self._pv12_org_status(dag, ctx)
        await self._pv13_backend(dag, ctx)
        return {"ok": True}

    def _pv01_schema(self, dag: list[dict]) -> None:
        if not isinstance(dag, list) or not dag:
            raise PlanValidationError("PV-01", "DAG 必须是非空数组")
        ids = set()
        for n in dag:
            if not isinstance(n, dict):
                raise PlanValidationError("PV-01", "节点必须是对象")
            for f in ("node_id", "node_type", "goal"):
                if f not in n:
                    raise PlanValidationError("PV-01", f"节点缺少字段 {f}", str(n))
            nid = n["node_id"]
            if nid in ids:
                raise PlanValidationError("PV-01", f"node_id 重复: {nid}")
            ids.add(nid)
            valid_types = ("agent_step", "review_task", "fix", "merge",
                           "manual_task", "condition")
            if n["node_type"] not in valid_types:
                raise PlanValidationError("PV-01", f"非法 node_type: {n['node_type']}")
            if not isinstance(n.get("depends_on", []), list):
                raise PlanValidationError("PV-01", "depends_on 必须是数组")

    async def _pv03_scale(self, dag: list[dict], company_id: str) -> None:
        # 从公司配置读取可配上限（设计 §PV-03：公司策略可配置默认值）
        max_nodes = 50
        max_depth_limit = 8
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT plan_validator_config FROM companies WHERE company_id = ?",
                (company_id,),
            )
            row = await cur.fetchone()
            if row:
                try:
                    cfg = json.loads(row["plan_validator_config"] or "{}")
                    max_nodes = cfg.get("max_nodes", max_nodes)
                    max_depth_limit = cfg.get("max_depth", max_depth_limit)
                except (json.JSONDecodeError, TypeError):
                    pass
        if len(dag) > max_nodes:
            raise PlanValidationError(
                "PV-03", f"节点数 {len(dag)} 超过上限 {max_nodes}"
            )
        if max_depth(dag) > max_depth_limit:
            raise PlanValidationError(
                "PV-03", f"依赖深度 {max_depth(dag)} 超过上限 {max_depth_limit}"
            )

    async def _load_assignees(self, dag: list[dict], ctx: ValidationContext) -> None:
        assignees = {
            n["assignee_employee_id"]
            for n in dag
            if n.get("assignee_employee_id")
        }
        if not assignees:
            return
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            placeholders = ",".join("?" for _ in assignees)
            cur = await db.execute(
                f"SELECT employee_id, department_id, status, capability_snapshot "
                f"FROM employees WHERE employee_id IN ({placeholders})",
                list(assignees),
            )
            for r in await cur.fetchall():
                ctx.assignee_departments[r["employee_id"]] = r["department_id"]
                ctx.assignee_status[r["employee_id"]] = r["status"]
                try:
                    snap = json.loads(r["capability_snapshot"] or "{}")
                except (json.JSONDecodeError, TypeError):
                    snap = {}
                tools = [
                    t.get("name")
                    for t in (snap.get("tools") or [])
                    if isinstance(t, dict)
                ]
                ctx.assignee_snapshot_tools[r["employee_id"]] = tools

    def _pv04_department_scope(self, dag: list[dict], ctx: ValidationContext) -> None:
        for n in dag:
            assignee = n.get("assignee_employee_id")
            if not assignee:
                continue
            dept = ctx.assignee_departments.get(assignee)
            if ctx.manager_scope == "dept":
                if dept != ctx.department_id:
                    raise PlanValidationError(
                        "PV-04",
                        f"节点 {n.get('node_id')} 的 assignee 不在 manager 部门范围",
                        f"dept={dept}, scope={ctx.department_id}",
                    )

    def _pv05_employee_status(self, dag: list[dict], ctx: ValidationContext) -> None:
        for n in dag:
            assignee = n.get("assignee_employee_id")
            if not assignee:
                continue
            status = ctx.assignee_status.get(assignee)
            if status != "active":
                raise PlanValidationError(
                    "PV-05", f"assignee {assignee} 状态非 active: {status}"
                )

    def _pv06_reviewer_independence(self, dag: list[dict]) -> None:
        for n in dag:
            if n.get("node_type") == "review_task":
                worker = n.get("worker_employee_id")
                reviewer = n.get("reviewer_employee_id") or n.get("assignee_employee_id")
                if worker and reviewer and worker == reviewer:
                    raise PlanValidationError(
                        "PV-06",
                        f"review 节点 {n.get('node_id')} 的 reviewer 不能是被审查的 worker",
                    )

    def _pv07_workspace(self, dag: list[dict]) -> None:
        valid = ("GitWorktree", "TaskWorkspace", "ReadOnly", "Restricted", "LocalWorkspace")
        for n in dag:
            ws = n.get("workspace_strategy")
            if ws and ws not in valid:
                raise PlanValidationError("PV-07", f"非法 workspace_strategy: {ws}")
            if n.get("node_type") == "manual_task" and ws in ("GitWorktree", "Restricted"):
                raise PlanValidationError("PV-07", "manual_task 不可分配写型 Workspace")

    def _pv08_budget_estimate(self, dag: list[dict], ctx: ValidationContext) -> None:
        if not ctx.currency or not ctx.budget_limit:
            return
        est = ctx.est_per_node * len(dag)
        if est > ctx.budget_limit:
            raise PlanValidationError(
                "PV-08", f"粗估成本 {est} 超出预算 {ctx.budget_limit}"
            )

    def _pv09_tool_binding(self, dag: list[dict], ctx: ValidationContext) -> None:
        for n in dag:
            tools = n.get("tools") or []
            assignee = n.get("assignee_employee_id")
            if not tools:
                continue
            snapshot_tools = set(ctx.assignee_snapshot_tools.get(assignee, []))
            for t in tools:
                if t not in snapshot_tools:
                    raise PlanValidationError(
                        "PV-09",
                        f"节点 {n.get('node_id')} 引用了 assignee 能力快照不存在的工具: {t}",
                    )

    def _pv10_output_schema(self, dag: list[dict]) -> None:
        forbidden = ("$ref", "additionalProperties", "allOf", "anyOf", "oneOf")
        for n in dag:
            schema_raw = n.get("outputs_schema")
            if not schema_raw:
                raise PlanValidationError(
                    "PV-10", f"节点 {n.get('node_id')} 缺少 outputs_schema"
                )
            try:
                schema = schema_raw if isinstance(schema_raw, dict) else json.loads(schema_raw)
            except (json.JSONDecodeError, TypeError):
                raise PlanValidationError(
                    "PV-10", f"节点 {n.get('node_id')} 的 outputs_schema 非合法 JSON"
                )
            text = json.dumps(schema)
            for kw in forbidden:
                if kw in text:
                    raise PlanValidationError("PV-10", f"outputs_schema 禁止关键字: {kw}")

    async def _pv11_hard_budget_provider(self, dag: list[dict], ctx: ValidationContext) -> None:
        if not ctx.currency:
            return
        hard_nodes = [n for n in dag if n.get("hard_budget")]
        if not hard_nodes:
            return
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT provider_id, model FROM provider_models
                   WHERE billing_mode = 'metered' AND enforces_output_cap = 1
                     AND (owner_company_id IS NULL OR owner_company_id = ?)""",
                (ctx.company_id,),
            )
            allowed = {(r["provider_id"], r["model"]) for r in await cur.fetchall()}
            cur2 = await db.execute(
                "SELECT provider_id FROM provider_budget_freezes "
                "WHERE company_id = ? AND status = 'active'",
                (ctx.company_id,),
            )
            frozen = {r["provider_id"] for r in await cur2.fetchall()}
        for n in hard_nodes:
            prov = n.get("provider_id")
            model = n.get("model")
            if (prov, model) not in allowed:
                raise PlanValidationError(
                    "PV-11",
                    f"硬预算节点 {n.get('node_id')} 的 Provider/Model "
                    f"不满足 metered+enforces_output_cap",
                )
            if prov in frozen:
                raise PlanValidationError("PV-11", f"Provider {prov} 已被公司冻结")

    async def _pv12_org_status(self, dag: list[dict], ctx: ValidationContext) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if ctx.manager_scope == "dept" and ctx.department_id:
                cur = await db.execute(
                    "SELECT status FROM departments WHERE department_id = ?",
                    (ctx.department_id,),
                )
                row = await cur.fetchone()
                if row is None or row["status"] != "active":
                    raise PlanValidationError(
                        "PV-12", f"manager 部门 {ctx.department_id} 非 active")
            depts = {d for d in ctx.assignee_departments.values() if d}
            for d in depts:
                cur = await db.execute(
                    "SELECT status FROM departments WHERE department_id = ?", (d,)
                )
                row = await cur.fetchone()
                if row is None or row["status"] != "active":
                    raise PlanValidationError("PV-12", f"部门 {d} 非 active")

    async def _pv13_backend(self, dag: list[dict], ctx: ValidationContext) -> None:
        from acos.backends.service import BackendScheduler

        scheduler = BackendScheduler(self._db_path)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            for n in dag:
                nt = n.get("node_type")
                backend_id = n.get("backend_id")
                if nt in ("manual_task", "condition"):
                    if backend_id is not None:
                        raise PlanValidationError(
                            "PV-13", f"{nt} 节点必须 backend_id=NULL")
                    continue
                if backend_id:
                    cur = await db.execute(
                        "SELECT company_id, status, health_status "
                        "FROM backends WHERE backend_id = ?",
                        (backend_id,),
                    )
                    row = await cur.fetchone()
                    if row is None:
                        raise PlanValidationError("PV-13", f"backend {backend_id} 不存在")
                    if row["company_id"] != ctx.company_id:
                        raise PlanValidationError("PV-13", f"backend {backend_id} 跨公司")
                    if row["status"] != "enabled":
                        raise PlanValidationError("PV-13", f"backend {backend_id} 非 enabled")
                    if row["health_status"] == "unhealthy":
                        raise PlanValidationError("PV-13", f"backend {backend_id} unhealthy")
                else:
                    backend = await scheduler.select_backend(ctx.company_id)
                    if backend is None:
                        raise PlanValidationError("PV-13", "无可用同公司 Backend（无默认可调度）")

    async def maybe_create_plan_approval(
        self, generation_id: str, company_id: str, risk_summary: str, plan_hash: str,
    ) -> Optional[str]:
        from acos.governance.models import Approval

        approval = Approval(
            company_id=company_id,
            task_id=None,
            employee_id="system",
            approval_type="plan_approval",
            risk_reason=risk_summary,
            requested_by="system",
            target_hash=plan_hash,
            target_snapshot=json.dumps({"generation_id": generation_id, "risk": risk_summary}),
        )
        approval = await self._gov.create_approval(approval)
        return approval.approval_id
