"""审批中心 RPC 方法集合（approval.* 命名空间）。"""

from __future__ import annotations

import aiosqlite
from typing import Any

from acos.governance.budget import BudgetService
from acos.governance.models import Approval, ApprovalRequest
from acos.governance.service import GovernanceService
from acos.organization.principal import resolve_actor
from acos.rpc.errors import AcosError
from acos.rpc.server import RPCServer


class ApprovalMethods:
    """审批中心相关的 RPC 方法（approval.*）。"""

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

        server.register_method("approval.list", self._list)
        server.register_method("approval.get", self._get)
        server.register_method("approval.resolve", self._resolve)
        server.register_method("approval.request", self._request)

    async def _list(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            raise AcosError(code="GOV-APPROVAL-NOT-FOUND", message="缺少 company_id")
        page = params.get("page") or {}
        limit = page.get("limit", 50)
        offset = page.get("offset", 0)
        items = await self._service.list_approvals(
            company_id, params.get("approval_type"), params.get("status"), limit, offset
        )
        return {
            "approvals": [
                {
                    "approval_id": a.approval_id,
                    "company_id": a.company_id,
                    "task_id": a.task_id,
                    "approval_type": a.approval_type,
                    "status": a.status,
                    "risk_reason": a.risk_reason,
                    "requested_by": a.requested_by,
                    "expiry": a.expiry,
                    "version": a.version,
                }
                for a in items
            ],
            "total": len(items),
            "limit": limit,
            "offset": offset,
        }

    async def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        approval_id = params.get("approval_id")
        if not approval_id:
            raise AcosError(code="GOV-APPROVAL-NOT-FOUND", message="缺少 approval_id")
        a = await self._service.get_approval(approval_id)
        if a is None:
            raise AcosError(code="GOV-APPROVAL-NOT-FOUND", message="审批不存在")
        return {
            "approval_id": a.approval_id,
            "company_id": a.company_id,
            "task_id": a.task_id,
            "approval_type": a.approval_type,
            "status": a.status,
            "target_hash": a.target_hash,
            "target_snapshot": a.target_snapshot,
            "risk_reason": a.risk_reason,
            "requested_by": a.requested_by,
            "approved_by": a.approved_by,
            "resolution": a.resolution,
            "reason": a.reason,
            "expiry": a.expiry,
            "currency": a.currency,
            "current_limit_micros": a.current_limit_micros,
            "requested_limit_micros": a.requested_limit_micros,
            "requested_delta_micros": a.requested_delta_micros,
            "usage_watermark_micros": a.usage_watermark_micros,
            "version": a.version,
        }

    async def _resolve(self, params: dict[str, Any]) -> dict[str, Any]:
        approval_id = params.get("approval_id")
        decision = params.get("decision")
        comment = params.get("comment")
        expected_version = params.get("expected_version", 1)
        if not approval_id or decision not in ("approve", "reject"):
            raise AcosError(code="APPR-DECISION-INVALID", message="缺少 approval_id 或 decision 非法")
        actor_type, actor_id = await self._resolve_actor()
        try:
            result = await self._service.resolve_approval(
                approval_id=approval_id,
                decision=decision,
                actor_id=actor_id,
                comment=comment,
                expected_version=expected_version,
                trace_id=params.get("trace_id", ""),
            )
        except AcosError as exc:
            await self._complete(params, "failed", error=exc.code)
            raise
        # 预算审批批准后应用 limit 修改
        if result.approval_type == "budget_approval" and decision == "approve":
            await self._budget.apply_budget_revision_on_approve(
                approval_id, actor_id, params.get("trace_id", "")
            )
        out = {"approval_id": result.approval_id, "status": result.status, "version": result.version}
        await self._complete(params, "succeeded", result=out)
        return out

    async def _request(self, params: dict[str, Any]) -> dict[str, Any]:
        """创建审批请求，绑定 target_ref/risk_summary，并生成对应 approval。"""
        company_id = params.get("company_id")
        approval_type = params.get("approval_type")
        target_ref = params.get("target_ref")
        if not all([company_id, approval_type, target_ref]):
            raise AcosError(code="APPR-REQUEST-INVALID", message="缺少 company_id/approval_type/target_ref")
        actor_type, actor_id = await self._resolve_actor()
        req = ApprovalRequest(
            company_id=company_id,
            approval_type=approval_type,
            task_id=params.get("task_id"),
            run_id=params.get("run_id"),
            node_id=params.get("node_id"),
            generation_id=params.get("generation_id"),
            target_ref=target_ref,
            target_skill=params.get("target_skill", params.get("target_gisk")),
            risk_summary=params.get("risk_summary"),
            target_hash=params.get("target_hash"),
            target_snapshot=params.get("target_snapshot"),
            requested_by=actor_id,
            expiry=params.get("expiry"),
        )
        req = await self._service.create_approval_request(req)
        # 同步创建一条 approval（统一的决议目标）
        approval = Approval(
            company_id=company_id,
            task_id=req.task_id,
            run_id=req.run_id,
            node_id=req.node_id,
            generation_id=req.generation_id,
            employee_id=actor_id,
            approval_type=approval_type,
            risk_reason=req.risk_summary,
            requested_by=actor_id,
            target_hash=req.target_hash,
            target_snapshot=req.target_snapshot,
            expiry=req.expiry,
            currency=params.get("currency"),
            current_limit_micros=params.get("current_limit_micros"),
            requested_limit_micros=params.get("requested_limit_micros"),
            requested_delta_micros=params.get("requested_delta_micros"),
            usage_watermark_micros=params.get("usage_watermark_micros", 0),
        )
        approval = await self._service.create_approval(approval)
        # 关联
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE approval_requests SET linked_approval_id = ? WHERE request_id = ?",
                (approval.approval_id, req.request_id),
            )
            await db.commit()
        out = {
            "request_id": req.request_id,
            "approval_id": approval.approval_id,
            "status": "pending",
        }
        await self._complete(params, "succeeded", result=out)
        return out

    # ── 内部工具 ────────────────────────────────────────────

    async def _resolve_actor(self) -> tuple[str, str]:
        async with aiosqlite.connect(self._db_path) as db:
            return await resolve_actor(db)

    async def _complete(self, params: dict[str, Any], status: str, result: dict | None = None, error: str | None = None) -> None:
        if self._server is None:
            return
        idempotency_key = params.get("idempotency_key")
        if not idempotency_key:
            return
        actor_type, actor_id = await self._resolve_actor()
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
