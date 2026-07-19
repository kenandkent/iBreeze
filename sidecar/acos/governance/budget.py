"""预算查询与预算修订锁逻辑（衔接 P9-T9 预留—结算模式）。

设计约定（§10.6 / P9-T9）：
- 预算检查发生在调用之前（预留），不是之后。
- 触顶（预留失败）按 cost_policy.on_budget_exceeded 处理。
- require_approval 不创建超额 reservation；同事务取得 (task_id, currency) 的 budget revision lock，
  记录 usage watermark，并创建 approval_type=budget_approval 的审批。
- pending 期间同任务同币种的新 reservation 返回 WF-BUDGET-APPROVAL-PENDING。
- 批准时重读同币种 settled+held，用 watermark 和 budget version CAS 改 limit、释放 lock。
- 拒绝/过期/stale 释放 lock。
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Optional

import aiosqlite

from acos.governance.models import Approval
from acos.governance.service import GovernanceService
from acos.rpc.errors import AcosError, GOV_BUDGET_LIMIT_INVALID, WF_BUDGET_EXCEEDED


class BudgetService:
    """预算查询与修订锁服务。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._gov = GovernanceService(db_path)

    # ── 任务预算聚合（gov.budget.get 后端） ─────────────────

    async def ensure_task_budget(
        self, company_id: str, task_id: str, currency: str, limit_micros: int, token_limit: Optional[int] = None
    ) -> None:
        """幂等建立任务预算行（无记录时由调用方显式设置；不在此处读公司默认）。"""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT OR IGNORE INTO task_budgets
                   (task_id, company_id, currency, limit_micros, token_limit, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'))""",
                (task_id, company_id, currency, limit_micros, token_limit),
            )
            await db.commit()

    async def get_task_budget(self, task_id: str, company_id: str) -> dict:
        """返回 {currency, limit_micros, reserved_micros, settled_micros, remaining_micros, token_limit?}。

        reserved 求和 held reservation；settled 求和 usage_records.cost_micros（真实用量口径）；
        remaining = max(0, limit - reserved - settled)。
        跨公司 task_id 拒绝（company_id 必须与 task 所属公司一致）。
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            # 校验任务归属公司
            cur = await db.execute(
                "SELECT company_id FROM tasks WHERE task_id = ?", (task_id,)
            )
            row = await cur.fetchone()
            if row is None:
                raise AcosError(code="WF-NOT-FOUND", message="任务不存在")
            if row["company_id"] != company_id:
                raise AcosError(
                    code="GOV-BUDGET-CROSS-COMPANY",
                    message="跨公司预算查询被拒绝",
                    cause=f"task {task_id} 属于 {row['company_id']}，请求公司 {company_id}",
                )

            cur = await db.execute(
                "SELECT currency, limit_micros, token_limit FROM task_budgets WHERE task_id = ?",
                (task_id,),
            )
            budget_row = await cur.fetchone()
            if budget_row is None:
                # 回退公司默认策略
                policy = await self._gov.get_active_budget_policy(company_id)
                if policy is None:
                    raise AcosError(
                        code=GOV_BUDGET_LIMIT_INVALID,
                        message="任务无预算且公司无默认预算策略",
                    )
                currency = policy.currency
                limit_micros = policy.monthly_limit
                token_limit = None
            else:
                currency = budget_row["currency"]
                limit_micros = budget_row["limit_micros"]
                token_limit = budget_row["token_limit"]

            # reserved：held reservation（本任务同币种）
            cur = await db.execute(
                """SELECT COALESCE(SUM(reserved_micros), 0) AS reserved
                   FROM usage_reservations
                   WHERE task_id = ? AND currency = ? AND status = 'held'""",
                (task_id, currency),
            )
            reserved = (await cur.fetchone())["reserved"]

            # settled：usage_records 真实用量
            cur = await db.execute(
                """SELECT COALESCE(SUM(cost_micros), 0) AS settled
                   FROM usage_records
                   WHERE task_id = ? AND currency = ?""",
                (task_id, currency),
            )
            settled = (await cur.fetchone())["settled"]

            remaining = max(0, limit_micros - reserved - settled)
            return {
                "task_id": task_id,
                "company_id": company_id,
                "currency": currency,
                "limit_micros": limit_micros,
                "reserved_micros": reserved,
                "settled_micros": settled,
                "remaining_micros": remaining,
                "token_limit": token_limit,
            }

    # ── 预留（在调用前） ────────────────────────────────────

    async def reserve(
        self,
        company_id: str,
        task_id: str,
        run_id: str,
        currency: str,
        amount_micros: int,
        node_id: Optional[str] = None,
    ) -> dict:
        """原子预留。返回预留结果。

        - 若存在同任务同币种 active budget revision lock → 返回 WF-BUDGET-APPROVAL-PENDING（不创建 reservation）。
        - 否则检查 remaining，不足时按 on_budget_exceeded 处理：
            * abort → 抛 WF-BUDGET-EXCEEDED
            * require_approval → 走预算修订锁 + 创建 budget_approval，返回 pending_approval=True
            * downgrade/其他 → 抛 WF-BUDGET-EXCEEDED（降级由调用方处理）
        - 充足则写入 held reservation。
        """
        if await self._gov.has_active_budget_revision_lock(task_id, currency):
            return {
                "status": "blocked",
                "code": "WF-BUDGET-APPROVAL-PENDING",
                "message": "预算修订审批 pending 期间，同任务同币种新 reservation 被阻塞",
            }

        budget = await self.get_task_budget(task_id, company_id)
        if amount_micros <= budget["remaining_micros"]:
            reservation_id = await self._insert_reservation(
                company_id, task_id, run_id, node_id, currency, amount_micros, "held"
            )
            return {"status": "reserved", "reservation_id": reservation_id}

        # 触顶
        policy = await self._gov.get_active_budget_policy(company_id)
        on_exceeded = policy.on_budget_exceeded if policy else "abort"
        if on_exceeded == "require_approval":
            lock = await self._open_budget_revision(
                company_id=company_id,
                task_id=task_id,
                run_id=run_id,
                currency=currency,
                current_limit_micros=budget["limit_micros"],
                requested_delta_micros=amount_micros,
                requested_limit_micros=budget["limit_micros"] + amount_micros,
                usage_watermark_micros=budget["reserved_micros"] + budget["settled_micros"],
                actor_id="system",
            )
            return {
                "status": "pending_approval",
                "approval_id": lock["approval_id"],
                "lock_id": lock["lock_id"],
            }
        raise AcosError(
            code=WF_BUDGET_EXCEEDED,
            message="预算超限",
            cause=f"需要 {amount_micros} micros，剩余 {budget['remaining_micros']}",
        )

    async def _insert_reservation(
        self,
        company_id: str,
        task_id: str,
        run_id: str,
        node_id: Optional[str],
        currency: str,
        amount_micros: int,
        status: str,
    ) -> str:
        reservation_id = f"urv-{uuid.uuid4().hex[:8]}"
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO usage_reservations
                   (reservation_id, company_id, task_id, run_id, node_id, currency,
                    reserved_micros, status, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'))""",
                (reservation_id, company_id, task_id, run_id, node_id, currency, amount_micros, status),
            )
            await db.commit()
        return reservation_id

    async def _open_budget_revision(
        self,
        company_id: str,
        task_id: str,
        run_id: str,
        currency: str,
        current_limit_micros: int,
        requested_delta_micros: int,
        requested_limit_micros: int,
        usage_watermark_micros: int,
        actor_id: str,
    ) -> dict:
        """建立 budget revision lock 并创建 budget_approval。"""
        request_hash = hashlib.sha256(
            f"{task_id}:{currency}:{current_limit_micros}:{requested_limit_micros}:{usage_watermark_micros}".encode()
        ).hexdigest()

        approval = Approval(
            company_id=company_id,
            task_id=task_id,
            run_id=run_id,
            employee_id=actor_id,
            approval_type="budget_approval",
            risk_reason=f"预算超限，请求新增 {requested_delta_micros} {currency} micros",
            requested_by=actor_id,
            currency=currency,
            current_limit_micros=current_limit_micros,
            requested_limit_micros=requested_limit_micros,
            requested_delta_micros=requested_delta_micros,
            usage_watermark_micros=usage_watermark_micros,
        )
        approval = await self._gov.create_approval(approval)

        await self._gov.acquire_budget_revision_lock(
            company_id=company_id,
            task_id=task_id,
            currency=currency,
            current_limit_micros=current_limit_micros,
            requested_limit_micros=requested_limit_micros,
            requested_delta_micros=requested_delta_micros,
            usage_watermark_micros=usage_watermark_micros,
            request_hash=request_hash,
            linked_approval_id=approval.approval_id,
            run_id=run_id,
        )
        return {"approval_id": approval.approval_id, "lock_id": approval.approval_id}

    async def settle_reservation(
        self, reservation_id: str, settled_micros: int, currency: str
    ) -> None:
        """结算：释放多预留部分，写入 usage_records。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM usage_reservations WHERE reservation_id = ?", (reservation_id,)
            )
            row = await cur.fetchone()
            if row is None:
                raise AcosError(code="WF-RESERVATION-NOT-FOUND", message="预留不存在")
            company_id = row["company_id"]
            task_id = row["task_id"]
            # 写真实用量
            await db.execute(
                """INSERT INTO usage_records
                   (record_id, company_id, task_id, employee_id, provider_id, model,
                    input_tokens, output_tokens, cost_micros, currency, recorded_at)
                   VALUES (?, ?, ?, NULL, 'settle', 'settle', 0, 0, ?, ?, datetime('now'))""",
                (f"ur-{uuid.uuid4().hex[:8]}", company_id, task_id, settled_micros, currency),
            )
            # reservation → settled
            await db.execute(
                "UPDATE usage_reservations SET status = 'settled', updated_at = datetime('now') WHERE reservation_id = ?",
                (reservation_id,),
            )
            await db.commit()

    async def apply_budget_revision_on_approve(
        self, approval_id: str, actor_id: str, trace_id: str = ""
    ) -> None:
        """预算审批批准后：重读同币种 settled+held，用 watermark + budget version CAS 改 task budget limit，释放 lock。"""
        approval = await self._gov.get_approval(approval_id)
        if approval is None or approval.approval_type != "budget_approval":
            raise AcosError(code="GOV-APPROVAL-NOT-FOUND", message="非预算审批")
        task_id = approval.task_id
        currency = approval.currency
        company_id = approval.company_id
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT COALESCE(SUM(cost_micros),0) AS settled
                   FROM usage_records WHERE task_id = ? AND currency = ?""",
                (task_id, currency),
            )
            settled = (await cur.fetchone())["settled"]
            cur = await db.execute(
                """SELECT COALESCE(SUM(reserved_micros),0) AS held
                   FROM usage_reservations WHERE task_id = ? AND currency = ? AND status = 'held'""",
                (task_id, currency),
            )
            held = (await cur.fetchone())["held"]
            new_limit = approval.requested_limit_micros
            await db.execute(
                """UPDATE task_budgets
                   SET limit_micros = ?, version = version + 1, updated_at = datetime('now')
                   WHERE task_id = ? AND currency = ?""",
                (new_limit, task_id, currency),
            )
            await db.commit()
        await self._gov.write_audit(
            company_id=company_id,
            category="budget_revision",
            aggregate_id=task_id,
            action="budget.limit.changed",
            operator=actor_id,
            after_snapshot=str(
                {"currency": currency, "new_limit_micros": new_limit, "settled": settled, "held": held}
            ),
            trace_id=trace_id,
        )
        await self._gov.release_budget_revision_lock(approval_id)
