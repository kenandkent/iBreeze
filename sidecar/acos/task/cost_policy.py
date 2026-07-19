"""成本分层与稳定性降级链（P9-T9，预算预留—结算模式）。

稳定性曲线（1-10 五段），统一降级链，对接 BudgetService.reserve/settle。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class DegradeDecision:
    action: str  # retry_same_tier / upgrade_tier / reassign / escalate_manager / human
    next_tier: Optional[str] = None
    next_employee_id: Optional[str] = None
    message: str = ""


_TIER_ORDER = ["free", "standard", "premium"]


def decide_degrade(
    stability_level: int,
    attempt: int,
    current_tier: str,
    dept_employees: list[str],
    current_employee_id: str,
    ceiling_tier: str = "premium",
) -> DegradeDecision:
    """统一降级链：同档重试 → 升配一档 → 改派本部门其他职员 → 升级本部门负责人 → 转人工。

    严格约束在发起子任务的部门内部，最高只到本部门负责人。
    """
    if stability_level <= 3:
        return DegradeDecision(action="human", message="稳定性低，直接转人工")
    if stability_level >= 7:
        if attempt <= 1:
            return DegradeDecision(action="retry_same_tier")
        if _index(current_tier) < _index(ceiling_tier):
            nt = _next_tier(current_tier, ceiling_tier)
            return DegradeDecision(action="upgrade_tier", next_tier=nt)
        return DegradeDecision(action="human", message="已达升配上限，转人工")
    if attempt <= 1:
        return DegradeDecision(action="retry_same_tier")
    if dept_employees:
        others = [e for e in dept_employees if e != current_employee_id]
        if others:
            return DegradeDecision(action="reassign", next_employee_id=others[0])
    return DegradeDecision(action="escalate_manager", message="升级本部门负责人")


def _index(tier: str) -> int:
    return _TIER_ORDER.index(tier) if tier in _TIER_ORDER else 0


def _next_tier(current: str, ceiling: str) -> str:
    i = _index(current)
    if i + 1 < len(_TIER_ORDER):
        nt = _TIER_ORDER[i + 1]
        if _index(nt) <= _index(ceiling):
            return nt
    return ceiling


class CostPolicy:
    """成本分层：角色→档位默认映射。"""

    @staticmethod
    def tier_for_role(role: str, stability_level: int = 5) -> str:
        if role == "manager":
            return "premium"
        if role == "worker":
            return "free" if stability_level <= 3 else "standard"
        return "standard"

    @staticmethod
    def worker_upgrade_ceiling() -> str:
        return "premium"
