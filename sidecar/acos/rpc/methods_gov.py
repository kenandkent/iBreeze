"""治理 RPC 方法集合（gov.* 命名空间）。"""

from __future__ import annotations

import aiosqlite
from typing import Any

from acos.governance.budget import BudgetService
from acos.governance.models import ApprovalType
from acos.governance.service import GovernanceService
from acos.organization.principal import resolve_actor
from acos.rpc.errors import AcosError
from acos.rpc.server import RPCServer


class GovMethods:
    """治理相关的 RPC 方法（gov.*）。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._service = GovernanceService(db_path)
        self._budget = BudgetService(db_path)
        self._server: RPCServer | None = None
        self._ctx_method: str = ""

    def register_to(self, server: RPCServer) -> None:
        self._server = server

        def _reg(method: str, handler: Any) -> None:
            async def _wrapper(params: dict[str, Any]) -> dict[str, Any]:
                self._ctx_method = method
                return await handler(params)

            server.register_method(method, _wrapper)

        # 预算策略
        _reg("gov.budgetPolicy.get", self._budget_policy_get)
        _reg("gov.budgetPolicy.update", self._budget_policy_update)
        # 预算查询 / 预留 / 修订
        _reg("gov.budget.get", self._budget_get)
        _reg("gov.budget.reserve", self._budget_reserve)
        _reg("gov.budget.revise", self._budget_revise)
        # 审批类型定义
        _reg("gov.approvalType.create", self._approval_type_create)
        _reg("gov.approvalType.list", self._approval_type_list)
        _reg("gov.approvalType.get", self._approval_type_get)
        _reg("gov.approvalType.update", self._approval_type_update)
        # 治理审计查询
        _reg("gov.audit.query", self._audit_query)

    # ── 预算策略（版本化 CAS） ──────────────────────────────

    async def _budget_policy_get(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            raise AcosError(code="GOV-BUDGET-POLICY-INVALID", message="缺少 company_id")
        policy = await self._service.get_active_budget_policy(company_id)
        if policy is None:
            return {"company_id": company_id, "exists": False}
        return {
            "company_id": policy.company_id,
            "policy_id": policy.policy_id,
            "name": policy.name,
            "monthly_limit": policy.monthly_limit,
            "per_task_limit": policy.per_task_limit,
            "currency": policy.currency,
            "on_budget_exceeded": policy.on_budget_exceeded,
            "version": policy.version,
            "exists": True,
        }

    async def _budget_policy_update(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        expected_policy_version = params.get("expected_policy_version", 1)
        updates = params.get("updates") or {}
        if not company_id:
            raise AcosError(code="GOV-BUDGET-POLICY-INVALID", message="缺少 company_id")
        actor_type, actor_id = await self._resolve(params)
        try:
            policy = await self._service.update_budget_policy(
                company_id=company_id,
                expected_policy_version=expected_policy_version,
                updates=updates,
                operator=actor_id,
                reason=params.get("reason"),
                trace_id=params.get("trace_id", ""),
            )
        except AcosError as exc:
            await self._complete(params, "failed", error=exc.code)
            raise
        result = {
            "policy_id": policy.policy_id,
            "version": policy.version,
            "monthly_limit": policy.monthly_limit,
            "currency": policy.currency,
        }
        await self._complete(params, "succeeded", result=result)
        return result

    # ── 预算查询 / 预留 / 修订 ──────────────────────────────

    async def _budget_get(self, params: dict[str, Any]) -> dict[str, Any]:
        task_id = params.get("task_id")
        company_id = params.get("company_id")
        if not task_id or not company_id:
            raise AcosError(code="GOV-BUDGET-POLICY-INVALID", message="缺少 task_id 或 company_id")
        return await self._budget.get_task_budget(task_id, company_id)

    async def _budget_reserve(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        task_id = params.get("task_id")
        run_id = params.get("run_id", "run-unknown")
        currency = params.get("currency")
        amount_micros = params.get("amount_micros")
        if not all([company_id, task_id, currency, isinstance(amount_micros, int)]):
            raise AcosError(code="GOV-BUDGET-LIMIT-INVALID", message="缺少必填字段或 amount_micros 非整数")
        return await self._budget.reserve(
            company_id=company_id,
            task_id=task_id,
            run_id=run_id,
            currency=currency,
            amount_micros=amount_micros,
            node_id=params.get("node_id"),
        )

    async def _budget_revise(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        task_id = params.get("task_id")
        currency = params.get("currency")
        requested_delta_micros = params.get("requested_delta_micros")
        if not all([company_id, task_id, currency, isinstance(requested_delta_micros, int)]):
            raise AcosError(code="GOV-BUDGET-LIMIT-INVALID", message="缺少必填字段")
        actor_type, actor_id = await self._resolve(params)
        budget = await self._budget.get_task_budget(task_id, company_id)
        await self._budget._open_budget_revision(
            company_id=company_id,
            task_id=task_id,
            run_id=params.get("run_id", "run-unknown"),
            currency=currency,
            current_limit_micros=budget["limit_micros"],
            requested_delta_micros=requested_delta_micros,
            requested_limit_micros=budget["limit_micros"] + requested_delta_micros,
            usage_watermark_micros=budget["reserved_micros"] + budget["settled_micros"],
            actor_id=actor_id,
        )
        locks = await self._list_active_locks(task_id, currency)
        result = {"status": "pending_approval", "lock": locks}
        await self._complete(params, "succeeded", result=result)
        return result

    # ── 审批类型定义 ────────────────────────────────────────

    async def _approval_type_create(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        name = params.get("name")
        category = params.get("category")
        if not company_id or not name or not category:
            raise AcosError(code="APPR-TYPE-INVALID", message="缺少 company_id/name/category")
        atype = ApprovalType(
            company_id=company_id,
            name=name,
            category=category,
            description=params.get("description"),
            requires_risk_summary=bool(params.get("requires_risk_summary", False)),
        )
        created = await self._service.create_approval_type(atype)
        result = {"approval_type_id": created.approval_type_id, "version": created.version}
        await self._complete(params, "succeeded", result=result)
        return result

    async def _approval_type_list(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            raise AcosError(code="APPR-TYPE-INVALID", message="缺少 company_id")
        items = await self._service.list_approval_types(company_id, params.get("category"))
        return {
            "types": [
                {
                    "approval_type_id": t.approval_type_id,
                    "name": t.name,
                    "category": t.category,
                    "requires_risk_summary": t.requires_risk_summary,
                    "status": t.status,
                    "version": t.version,
                }
                for t in items
            ]
        }

    async def _approval_type_get(self, params: dict[str, Any]) -> dict[str, Any]:
        atype_id = params.get("approval_type_id")
        if not atype_id:
            raise AcosError(code="APPR-TYPE-INVALID", message="缺少 approval_type_id")
        t = await self._service.get_approval_type(atype_id)
        if t is None:
            raise AcosError(code="APPR-TYPE-NOT-FOUND", message="审批类型不存在")
        return {
            "approval_type_id": t.approval_type_id,
            "company_id": t.company_id,
            "name": t.name,
            "category": t.category,
            "description": t.description,
            "requires_risk_summary": t.requires_risk_summary,
            "status": t.status,
            "version": t.version,
        }

    async def _approval_type_update(self, params: dict[str, Any]) -> dict[str, Any]:
        atype_id = params.get("approval_type_id")
        expected_version = params.get("expected_version", 1)
        updates = params.get("updates") or {}
        if not atype_id:
            raise AcosError(code="APPR-TYPE-INVALID", message="缺少 approval_type_id")
        actor_type, actor_id = await self._resolve(params)
        t = await self._service.update_approval_type(
            approval_type_id=atype_id,
            expected_version=expected_version,
            updates=updates,
            operator=actor_id,
            trace_id=params.get("trace_id", ""),
        )
        result = {"approval_type_id": t.approval_type_id, "version": t.version}
        await self._complete(params, "succeeded", result=result)
        return result

    # ── 治理审计查询 ────────────────────────────────────────

    async def _audit_query(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        category = params.get("type")
        page = params.get("page") or {}
        limit = page.get("limit", 50)
        offset = page.get("offset", 0)
        if not company_id:
            raise AcosError(code="GOV-AUDIT-INVALID", message="缺少 company_id")
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            conds = ["company_id = ?"]
            vals: list[Any] = [company_id]
            if category:
                conds.append("category = ?")
                vals.append(category)
            where = " AND ".join(conds)
            cursor = await db.execute(
                f"SELECT * FROM governance_audit WHERE {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                vals + [limit, offset],
            )
            rows = [dict(r) for r in await cursor.fetchall()]
            count_cur = await db.execute(
                f"SELECT COUNT(*) AS c FROM governance_audit WHERE {where}", vals
            )
            total = (await count_cur.fetchone())["c"]
        return {"items": rows, "total": total, "limit": limit, "offset": offset}

    # ── 内部工具 ────────────────────────────────────────────

    async def _resolve(self, params: dict[str, Any]) -> tuple[str, str]:
        async with aiosqlite.connect(self._db_path) as db:
            return await resolve_actor(db, params.get("_actor_context"))

    async def _complete(self, params: dict[str, Any], status: str, result: dict | None = None, error: str | None = None) -> None:
        if self._server is None:
            return
        idempotency_key = params.get("idempotency_key")
        if not idempotency_key:
            return
        actor_type, actor_id = await self._resolve(params)
        conn = await aiosqlite.connect(self._db_path)
        try:
            await self._server.complete_idempotency(
                conn=conn,
                company_id=params.get("company_id", ""),
                actor_type=actor_type,
                actor_id=actor_id,
                method=self._ctx_method,
                idempotency_key=idempotency_key,
                status=status,
                result=result,
                error=error,
            )
        finally:
            await conn.close()

    async def _list_active_locks(self, task_id: str, currency: str) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM budget_revision_locks WHERE task_id = ? AND currency = ? AND status = 'active'",
                (task_id, currency),
            )
            return [dict(r) for r in await cur.fetchall()]
