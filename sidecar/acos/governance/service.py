"""治理服务：预算策略、审批、用量追踪、预算修订锁。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from acos.governance.models import Approval, ApprovalRequest, ApprovalType, BudgetPolicy, BudgetRevisionLock, UsageRecord
from acos.rpc.errors import (
    AcosError,
    GOV_APPROVAL_REJECTED,
    GOV_BUDGET_CURRENCY_INVALID,
    GOV_BUDGET_LIMIT_INVALID,
    SYS_OPTIMISTIC_LOCK_CONFLICT,
)

# ISO-4217 三位字母币种（最小可用集，真实校验截断到已知活跃币种）
_VALID_CURRENCIES = {
    "USD", "EUR", "GBP", "JPY", "CNY", "CHF", "CAD", "AUD", "HKD", "SGD",
    "SEK", "NOK", "DKK", "NZD", "KRW", "INR", "BRL", "MXN", "ZAR", "RUB",
}

# int64 micros 上界（9,223,372,036,854,775,807）
_INT64_MAX = 9_223_372_036_854_775_807


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_policy(row: aiosqlite.Row) -> BudgetPolicy:
    return BudgetPolicy(
        policy_id=row["policy_id"],
        company_id=row["company_id"],
        name=row["name"],
        monthly_limit=row["monthly_limit"],
        per_task_limit=row["per_task_limit"],
        currency=row["currency"],
        on_budget_exceeded=row["on_budget_exceeded"],
        version=row["version"],
    )


def _row_to_approval(row: aiosqlite.Row) -> Approval:
    return Approval(
        approval_id=row["approval_id"],
        company_id=row["company_id"],
        task_id=row["task_id"],
        node_id=row["node_id"] if "node_id" in row.keys() else None,
        run_id=row["run_id"] if "run_id" in row.keys() else None,
        generation_id=row["generation_id"] if "generation_id" in row.keys() else None,
        employee_id=row["employee_id"],
        approval_type=row["approval_type"],
        status=row["status"],
        target_hash=row["target_hash"] if "target_hash" in row.keys() else None,
        target_snapshot=row["target_snapshot"] if "target_snapshot" in row.keys() else None,
        risk_reason=row["risk_reason"] if "risk_reason" in row.keys() else None,
        requested_by=row["requested_by"],
        approved_by=row["approved_by"] if "approved_by" in row.keys() else None,
        resolution=row["resolution"] if "resolution" in row.keys() else None,
        reason=row["reason"] if "reason" in row.keys() else None,
        expiry=row["expiry"] if "expiry" in row.keys() else None,
        currency=row["currency"] if "currency" in row.keys() else None,
        current_limit_micros=row["current_limit_micros"] if "current_limit_micros" in row.keys() else None,
        requested_limit_micros=row["requested_limit_micros"] if "requested_limit_micros" in row.keys() else None,
        requested_delta_micros=row["requested_delta_micros"] if "requested_delta_micros" in row.keys() else None,
        usage_watermark_micros=row["usage_watermark_micros"] if "usage_watermark_micros" in row.keys() else 0,
        version=row["version"],
    )


def _row_to_approval_type(row: aiosqlite.Row) -> ApprovalType:
    return ApprovalType(
        approval_type_id=row["approval_type_id"],
        company_id=row["company_id"],
        name=row["name"],
        category=row["category"],
        description=row["description"] if "description" in row.keys() else None,
        requires_risk_summary=bool(row["requires_risk_summary"]),
        status=row["status"],
        version=row["version"],
    )


def _validate_currency(currency: str) -> None:
    if not currency or currency not in _VALID_CURRENCIES:
        raise AcosError(
            code=GOV_BUDGET_CURRENCY_INVALID,
            message=f"无效币种: {currency!r}",
            cause="currency 必须是 ISO-4217 三位字母代码",
            suggestion="使用受支持的法币代码，例如 USD/CNY",
        )


def _validate_micros(value: int, field: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise AcosError(
            code=GOV_BUDGET_LIMIT_INVALID,
            message=f"{field} 必须是整数 micros",
            cause="金额必须使用 int64 micros，禁止 float",
        )
    if value < 0:
        raise AcosError(
            code=GOV_BUDGET_LIMIT_INVALID,
            message=f"{field} 不能为负",
            cause="预算金额必须非负",
        )
    if value > _INT64_MAX:
        raise AcosError(
            code=GOV_BUDGET_LIMIT_INVALID,
            message=f"{field} 溢出 int64",
            cause=f"金额不得超过 {_INT64_MAX}",
        )


class GovernanceService:
    """治理服务。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    # ── 审计（append-only） ────────────────────────────────

    async def write_audit(
        self,
        company_id: str,
        category: str,
        aggregate_id: str,
        action: str,
        operator: str,
        before_snapshot: Optional[str] = None,
        after_snapshot: Optional[str] = None,
        reason: Optional[str] = None,
        trace_id: str = "",
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO governance_audit
                   (audit_id, company_id, category, aggregate_id, action,
                    before_snapshot, after_snapshot, operator, reason, trace_id, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"gau-{uuid.uuid4().hex[:12]}",
                    company_id,
                    category,
                    aggregate_id,
                    action,
                    before_snapshot,
                    after_snapshot,
                    operator,
                    reason,
                    trace_id or uuid.uuid4().hex,
                    _now(),
                ),
            )
            await db.commit()

    # ── 预算策略（版本化） ──────────────────────────────────

    async def create_budget_policy(self, policy: BudgetPolicy) -> BudgetPolicy:
        _validate_currency(policy.currency)
        _validate_micros(policy.monthly_limit, "monthly_limit")
        _validate_micros(policy.per_task_limit, "per_task_limit")
        if not policy.policy_id:
            policy.policy_id = f"bp-{uuid.uuid4().hex[:8]}"
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO budget_policies
                   (policy_id, company_id, name, monthly_limit, per_task_limit,
                    currency, on_budget_exceeded, version, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'active', ?)""",
                (
                    policy.policy_id,
                    policy.company_id,
                    policy.name,
                    policy.monthly_limit,
                    policy.per_task_limit,
                    policy.currency,
                    policy.on_budget_exceeded,
                    now,
                ),
            )
            await db.commit()
        return policy

    async def get_active_budget_policy(self, company_id: str) -> Optional[BudgetPolicy]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM budget_policies
                   WHERE company_id = ? AND status = 'active'
                   ORDER BY version DESC LIMIT 1""",
                (company_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return _row_to_policy(row)

    async def update_budget_policy(
        self,
        company_id: str,
        expected_policy_version: int,
        updates: dict,
        operator: str = "system",
        reason: Optional[str] = None,
        trace_id: str = "",
    ) -> BudgetPolicy:
        """版本化更新：CAS 比对当前 active 版本，supersede 旧版并插入新版。"""
        if "currency" in updates and updates["currency"] is not None:
            _validate_currency(updates["currency"])
        if "monthly_limit" in updates and updates["monthly_limit"] is not None:
            _validate_micros(updates["monthly_limit"], "monthly_limit")
        if "per_task_limit" in updates and updates["per_task_limit"] is not None:
            _validate_micros(updates["per_task_limit"], "per_task_limit")

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM budget_policies
                   WHERE company_id = ? AND status = 'active'
                   ORDER BY version DESC LIMIT 1""",
                (company_id,),
            )
            current = await cursor.fetchone()
            if current is None:
                raise AcosError(
                    code=GOV_BUDGET_LIMIT_INVALID,
                    message="公司不存在活跃预算策略",
                    cause="请先创建预算策略",
                )
            if current["version"] != expected_policy_version:
                raise AcosError(
                    code=SYS_OPTIMISTIC_LOCK_CONFLICT,
                    message="预算策略版本冲突",
                    cause=f"期望版本 {expected_policy_version}，实际 {current['version']}",
                    suggestion="请重新读取最新策略后重试",
                )

            before_snapshot = dict(current)
            policy_id = f"bp-{uuid.uuid4().hex[:8]}"
            name = updates.get("name", current["name"])
            monthly_limit = updates.get("monthly_limit", current["monthly_limit"])
            per_task_limit = updates.get("per_task_limit", current["per_task_limit"])
            currency = updates.get("currency", current["currency"])
            on_budget_exceeded = updates.get("on_budget_exceeded", current["on_budget_exceeded"])
            now = _now()

            # supersede 旧版
            await db.execute(
                "UPDATE budget_policies SET status = 'superseded' WHERE policy_id = ?",
                (current["policy_id"],),
            )
            # 插入新版（version 自增）
            await db.execute(
                """INSERT INTO budget_policies
                   (policy_id, company_id, name, monthly_limit, per_task_limit,
                    currency, on_budget_exceeded, version, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
                (
                    policy_id,
                    company_id,
                    name,
                    monthly_limit,
                    per_task_limit,
                    currency,
                    on_budget_exceeded,
                    current["version"] + 1,
                    now,
                ),
            )
            await db.commit()

            await self.write_audit(
                company_id=company_id,
                category="budget",
                aggregate_id=policy_id,
                action="budget_policy.update",
                operator=operator,
                before_snapshot=str(before_snapshot),
                after_snapshot=str(
                    {
                        "policy_id": policy_id,
                        "version": current["version"] + 1,
                        "monthly_limit": monthly_limit,
                        "per_task_limit": per_task_limit,
                        "currency": currency,
                        "on_budget_exceeded": on_budget_exceeded,
                    }
                ),
                reason=reason,
                trace_id=trace_id,
            )

        result = await self.get_active_budget_policy(company_id)
        assert result is not None
        return result

    async def check_budget(self, company_id: str, estimated_cost: int) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT monthly_limit FROM budget_policies
                   WHERE company_id = ? AND status = 'active'
                   ORDER BY version DESC LIMIT 1""",
                (company_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return True

            monthly_limit = row["monthly_limit"]
            if monthly_limit == 0:
                return True

            now = datetime.now(timezone.utc)
            period_start = now.strftime("%Y-%m-01")
            cursor2 = await db.execute(
                """SELECT COALESCE(SUM(cost_micros), 0) as total_cost
                   FROM usage_records
                   WHERE company_id = ? AND recorded_at >= ?""",
                (company_id, period_start),
            )
            usage_row = await cursor2.fetchone()
            total_cost = usage_row["total_cost"]
            return (total_cost + estimated_cost) <= monthly_limit

    async def record_usage(self, record: UsageRecord) -> None:
        if not record.record_id:
            record.record_id = f"ur-{uuid.uuid4().hex[:8]}"
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO usage_records
                   (record_id, company_id, task_id, employee_id, provider_id,
                    model, input_tokens, output_tokens, cost_micros, currency,
                    recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.record_id,
                    record.company_id,
                    record.task_id,
                    record.employee_id,
                    record.provider_id,
                    record.model,
                    record.input_tokens,
                    record.output_tokens,
                    record.cost_micros,
                    record.currency,
                    _now(),
                ),
            )
            await db.commit()

    async def get_usage_summary(self, company_id: str, period: str = "month") -> dict:
        now = datetime.now(timezone.utc)
        if period == "month":
            period_start = now.strftime("%Y-%m-01")
        elif period == "week":
            days_since_monday = now.weekday()
            period_start = (now - __import__("datetime").timedelta(days=days_since_monday)).strftime("%Y-%m-%d")
        else:
            period_start = now.strftime("%Y-01-01")

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT
                    COUNT(*) as record_count,
                    COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                    COALESCE(SUM(output_tokens), 0) as total_output_tokens,
                    COALESCE(SUM(cost_micros), 0) as total_cost_micros
                   FROM usage_records
                   WHERE company_id = ? AND recorded_at >= ?""",
                (company_id, period_start),
            )
            row = await cursor.fetchone()
            return {
                "company_id": company_id,
                "period": period,
                "period_start": period_start,
                "record_count": row["record_count"],
                "total_input_tokens": row["total_input_tokens"],
                "total_output_tokens": row["total_output_tokens"],
                "total_cost_micros": row["total_cost_micros"],
            }

    # ── 审批类型定义 ────────────────────────────────────────

    async def create_approval_type(self, atype: ApprovalType) -> ApprovalType:
        if not atype.approval_type_id:
            atype.approval_type_id = f"at-{uuid.uuid4().hex[:8]}"
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO approval_types
                   (approval_type_id, company_id, name, category, description,
                    requires_risk_summary, status, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'active', 1, ?, ?)""",
                (
                    atype.approval_type_id,
                    atype.company_id,
                    atype.name,
                    atype.category,
                    atype.description,
                    int(atype.requires_risk_summary),
                    now,
                    now,
                ),
            )
            await db.commit()
        return atype

    async def list_approval_types(self, company_id: str, category: Optional[str] = None) -> list[ApprovalType]:
        conds = ["company_id = ?"]
        vals: list[object] = [company_id]
        if category:
            conds.append("category = ?")
            vals.append(category)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM approval_types WHERE {' AND '.join(conds)} ORDER BY created_at DESC",
                vals,
            )
            return [_row_to_approval_type(r) for r in await cursor.fetchall()]

    async def get_approval_type(self, approval_type_id: str) -> Optional[ApprovalType]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM approval_types WHERE approval_type_id = ?",
                (approval_type_id,),
            )
            row = await cursor.fetchone()
            return _row_to_approval_type(row) if row else None

    async def update_approval_type(
        self,
        approval_type_id: str,
        expected_version: int,
        updates: dict,
        operator: str = "system",
        trace_id: str = "",
    ) -> ApprovalType:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM approval_types WHERE approval_type_id = ?",
                (approval_type_id,),
            )
            current = await cursor.fetchone()
            if current is None:
                raise AcosError(code="APPR-TYPE-NOT-FOUND", message="审批类型不存在")
            if current["version"] != expected_version:
                raise AcosError(
                    code=SYS_OPTIMISTIC_LOCK_CONFLICT,
                    message="审批类型版本冲突",
                    cause=f"期望 {expected_version}，实际 {current['version']}",
                )
            sets = ["version = version + 1", "updated_at = ?"]
            vals: list[object] = [_now()]
            if "name" in updates and updates["name"] is not None:
                sets.append("name = ?")
                vals.append(updates["name"])
            if "description" in updates and updates["description"] is not None:
                sets.append("description = ?")
                vals.append(updates["description"])
            if "status" in updates and updates["status"] is not None:
                sets.append("status = ?")
                vals.append(updates["status"])
            if "requires_risk_summary" in updates and updates["requires_risk_summary"] is not None:
                sets.append("requires_risk_summary = ?")
                vals.append(int(updates["requires_risk_summary"]))
            vals.append(approval_type_id)
            await db.execute(
                f"UPDATE approval_types SET {', '.join(sets)} WHERE approval_type_id = ?",
                vals,
            )
            await db.commit()
            await self.write_audit(
                company_id=current["company_id"],
                category="approval_type",
                aggregate_id=approval_type_id,
                action="approval_type.update",
                operator=operator,
                after_snapshot=str(updates),
                trace_id=trace_id,
            )
        result = await self.get_approval_type(approval_type_id)
        assert result is not None
        return result

    # ── 审批请求（绑定 target_ref / risk_summary） ──────────

    async def create_approval_request(self, req: ApprovalRequest) -> ApprovalRequest:
        if not req.request_id:
            req.request_id = f"ar-{uuid.uuid4().hex[:8]}"
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO approval_requests
                   (request_id, company_id, approval_type, task_id, run_id, node_id,
                    generation_id, target_ref, target_gisk, risk_summary, target_hash,
                    target_snapshot, requested_by, status, expiry, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, 1, ?, ?)""",
                (
                    req.request_id,
                    req.company_id,
                    req.approval_type,
                    req.task_id,
                    req.run_id,
                    req.node_id,
                    req.generation_id,
                    req.target_ref,
                    req.target_gisk,
                    req.risk_summary,
                    req.target_hash,
                    req.target_snapshot,
                    req.requested_by,
                    req.expiry,
                    now,
                    now,
                ),
            )
            await db.commit()
        return req

    async def get_approval_request(self, request_id: str) -> Optional[ApprovalRequest]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM approval_requests WHERE request_id = ?", (request_id,)
            )
            row = await cursor.fetchone()
            return _row_to_approval_request(row) if row else None

    # ── 审批生命周期 ────────────────────────────────────────

    async def create_approval(self, approval: Approval) -> Approval:
        if not approval.approval_id:
            approval.approval_id = f"ap-{uuid.uuid4().hex[:8]}"
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO approvals
                   (approval_id, company_id, task_id, node_id, run_id, generation_id,
                    employee_id, approval_type, status, target_hash, target_snapshot,
                    risk_reason, requested_by, approved_by, resolution, reason, expiry,
                    currency, current_limit_micros, requested_limit_micros,
                    requested_delta_micros, usage_watermark_micros, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, NULL, NULL, NULL, ?,
                           ?, ?, ?, ?, ?, 1, ?, ?)""",
                (
                    approval.approval_id,
                    approval.company_id,
                    approval.task_id,
                    approval.node_id,
                    approval.run_id,
                    approval.generation_id,
                    approval.employee_id,
                    approval.approval_type,
                    approval.target_hash,
                    approval.target_snapshot,
                    approval.risk_reason,
                    approval.requested_by,
                    approval.expiry,
                    approval.currency,
                    approval.current_limit_micros,
                    approval.requested_limit_micros,
                    approval.requested_delta_micros,
                    approval.usage_watermark_micros,
                    now,
                    now,
                ),
            )
            await db.commit()
        return approval

    # 兼容旧测试 / 简单调用：直接 approve / reject（CAS version=1 默认）
    # 保持旧行为：冲突/非 pending 抛 ValueError("not found or version mismatch")
    async def approve(
        self, approval_id: str, approved_by: str, expected_version: int = 1
    ) -> Approval:
        try:
            return await self.resolve_approval(
                approval_id=approval_id,
                decision="approve",
                actor_id=approved_by,
                expected_version=expected_version,
            )
        except AcosError:
            raise ValueError(f"Approval {approval_id} not found or version mismatch")

    async def reject(
        self,
        approval_id: str,
        approved_by: str,
        expected_version: int = 1,
        reason: str = "",
    ) -> Approval:
        try:
            return await self.resolve_approval(
                approval_id=approval_id,
                decision="reject",
                actor_id=approved_by,
                comment=reason,
                expected_version=expected_version,
            )
        except AcosError:
            raise ValueError(f"Approval {approval_id} not found or version mismatch")

    async def list_approvals(
        self,
        company_id: str,
        approval_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Approval]:
        conds = ["company_id = ?"]
        vals: list[object] = [company_id]
        if approval_type:
            conds.append("approval_type = ?")
            vals.append(approval_type)
        if status:
            conds.append("status = ?")
            vals.append(status)
        vals.extend([limit, offset])
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM approvals WHERE {' AND '.join(conds)} "
                f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
                vals,
            )
            return [_row_to_approval(r) for r in await cursor.fetchall()]

    async def get_approval(self, approval_id: str) -> Optional[Approval]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
            )
            row = await cursor.fetchone()
            return _row_to_approval(row) if row else None

    @staticmethod
    def _is_expired(expiry: Optional[str]) -> bool:
        if not expiry:
            return False
        try:
            exp = datetime.fromisoformat(expiry)
        except ValueError:
            return False
        return exp <= datetime.now(timezone.utc)

    async def resolve_approval(
        self,
        approval_id: str,
        decision: str,  # "approve" | "reject"
        actor_id: str,
        comment: Optional[str] = None,
        expected_version: int = 1,
        trace_id: str = "",
    ) -> Approval:
        """对 pending 审批做 CAS 决议。

        - 过期审批不可决议（转 expired）。
        - budget 类型批准时按 watermark/budget version 改 limit（由调用方在事务外完成 limit 修改，
          此处仅标记 approved 并释放 lock）。
        """
        if decision not in ("approve", "reject"):
            raise AcosError(code="APPR-DECISION-INVALID", message="decision 必须是 approve 或 reject")

        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                raise AcosError(code="GOV-APPROVAL-NOT-FOUND", message="审批不存在")
            if row["status"] != "pending":
                raise AcosError(
                    code="GOV-APPROVAL-STALE",
                    message="审批已非 pending，不可决议",
                    cause=f"当前状态 {row['status']}",
                )
            if row["version"] != expected_version:
                raise AcosError(
                    code=SYS_OPTIMISTIC_LOCK_CONFLICT,
                    message="审批版本冲突",
                    cause=f"期望 {expected_version}，实际 {row['version']}",
                )
            if self._is_expired(row["expiry"]):
                await db.execute(
                    "UPDATE approvals SET status = 'expired', version = version + 1, updated_at = ? WHERE approval_id = ?",
                    (now, approval_id),
                )
                await db.commit()
                raise AcosError(
                    code="GOV-APPROVAL-EXPIRED",
                    message="审批已过期",
                    cause="超过 expiry 不可决议",
                )

            new_status = "approved" if decision == "approve" else "rejected"
            await db.execute(
                """UPDATE approvals
                   SET status = ?, approved_by = ?, resolution = ?, reason = ?,
                       version = version + 1, updated_at = ?
                   WHERE approval_id = ? AND status = 'pending' AND version = ?""",
                (new_status, actor_id, decision, comment, now, approval_id, expected_version),
            )
            await db.commit()

            await self.write_audit(
                company_id=row["company_id"],
                category="approval",
                aggregate_id=approval_id,
                action=f"approval.{decision}",
                operator=actor_id,
                after_snapshot=str({"decision": decision, "comment": comment}),
                trace_id=trace_id,
            )

            # 若为预算审批，释放对应的 budget revision lock
            if row["approval_type"] == "budget_approval" and decision == "approve":
                await db.execute(
                    "UPDATE budget_revision_locks SET status = 'released', updated_at = ? WHERE linked_approval_id = ? AND status = 'active'",
                    (now, approval_id),
                )
                await db.commit()
            elif row["approval_type"] == "budget_approval" and decision == "reject":
                await db.execute(
                    "UPDATE budget_revision_locks SET status = 'released', updated_at = ? WHERE linked_approval_id = ? AND status = 'active'",
                    (now, approval_id),
                )
                await db.commit()

            cursor2 = await db.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
            )
            result_row = await cursor2.fetchone()
            return _row_to_approval(result_row)

    # ── 预算修订锁（与 P9-T9 衔接） ─────────────────────────

    async def acquire_budget_revision_lock(
        self,
        company_id: str,
        task_id: str,
        currency: str,
        current_limit_micros: int,
        requested_limit_micros: int,
        requested_delta_micros: int,
        usage_watermark_micros: int,
        request_hash: str,
        linked_approval_id: str,
        run_id: Optional[str] = None,
    ) -> BudgetRevisionLock:
        """建立预算修订锁。调用方应先检查是否已存在 active lock（见 has_active_budget_revision_lock）。"""
        _validate_currency(currency)
        lock_id = f"brl-{uuid.uuid4().hex[:8]}"
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO budget_revision_locks
                   (lock_id, company_id, task_id, currency, run_id,
                    current_limit_micros, requested_limit_micros, requested_delta_micros,
                    usage_watermark_micros, request_hash, linked_approval_id, status, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 1, ?, ?)""",
                (
                    lock_id,
                    company_id,
                    task_id,
                    currency,
                    run_id,
                    current_limit_micros,
                    requested_limit_micros,
                    requested_delta_micros,
                    usage_watermark_micros,
                    request_hash,
                    linked_approval_id,
                    now,
                    now,
                ),
            )
            await db.commit()
        return BudgetRevisionLock(
            lock_id=lock_id,
            company_id=company_id,
            task_id=task_id,
            currency=currency,
            run_id=run_id,
            current_limit_micros=current_limit_micros,
            requested_limit_micros=requested_limit_micros,
            requested_delta_micros=requested_delta_micros,
            usage_watermark_micros=usage_watermark_micros,
            request_hash=request_hash,
            linked_approval_id=linked_approval_id,
            status="active",
        )

    async def has_active_budget_revision_lock(self, task_id: str, currency: str) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """SELECT 1 FROM budget_revision_locks
                   WHERE task_id = ? AND currency = ? AND status = 'active' LIMIT 1""",
                (task_id, currency),
            )
            return await cursor.fetchone() is not None

    async def release_budget_revision_lock(self, linked_approval_id: str) -> None:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE budget_revision_locks SET status = 'released', updated_at = ? WHERE linked_approval_id = ? AND status = 'active'",
                (now, linked_approval_id),
            )
            await db.commit()


def _row_to_approval_request(row: aiosqlite.Row) -> ApprovalRequest:
    return ApprovalRequest(
        request_id=row["request_id"],
        company_id=row["company_id"],
        approval_type=row["approval_type"],
        task_id=row["task_id"] if "task_id" in row.keys() else None,
        run_id=row["run_id"] if "run_id" in row.keys() else None,
        node_id=row["node_id"] if "node_id" in row.keys() else None,
        generation_id=row["generation_id"] if "generation_id" in row.keys() else None,
        target_ref=row["target_ref"],
        target_gisk=row["target_gisk"] if "target_gisk" in row.keys() else None,
        risk_summary=row["risk_summary"] if "risk_summary" in row.keys() else None,
        target_hash=row["target_hash"] if "target_hash" in row.keys() else None,
        target_snapshot=row["target_snapshot"] if "target_snapshot" in row.keys() else None,
        requested_by=row["requested_by"],
        linked_approval_id=row["linked_approval_id"] if "linked_approval_id" in row.keys() else None,
        status=row["status"],
        expiry=row["expiry"] if "expiry" in row.keys() else None,
        version=row["version"],
    )
