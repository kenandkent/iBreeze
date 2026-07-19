"""GovernanceService 测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.governance.models import Approval, BudgetPolicy, UsageRecord
from acos.governance.service import GovernanceService
from acos.store.migrator import Migrator


@pytest.fixture
async def db_path(tmp_path: Path) -> str:
    p = tmp_path / "test.db"
    migrator = Migrator(str(p))
    await migrator.run_pending_migrations(
        str(Path(__file__).resolve().parents[2] / "migrations")
    )
    return str(p)


@pytest.fixture
def svc(db_path: str) -> GovernanceService:
    return GovernanceService(db_path)


# ── BudgetPolicy ──


async def test_create_budget_policy(svc: GovernanceService) -> None:
    policy = BudgetPolicy(
        company_id="comp-1",
        name="default",
        monthly_limit=1000000,
        per_task_limit=50000,
    )
    created = await svc.create_budget_policy(policy)
    assert created.policy_id.startswith("bp-")


async def test_check_budget_no_policy(svc: GovernanceService) -> None:
    ok = await svc.check_budget("comp-nopolicy", 1000)
    assert ok is True


async def test_check_budget_within_limit(svc: GovernanceService) -> None:
    await svc.create_budget_policy(
        BudgetPolicy(company_id="comp-1", name="test", monthly_limit=1000000)
    )
    ok = await svc.check_budget("comp-1", 500000)
    assert ok is True


async def test_check_budget_exceeded(svc: GovernanceService) -> None:
    await svc.create_budget_policy(
        BudgetPolicy(company_id="comp-1", name="test", monthly_limit=100)
    )
    await svc.record_usage(
        UsageRecord(
            company_id="comp-1",
            provider_id="openai",
            model="gpt-4",
            cost_micros=80,
        )
    )
    ok = await svc.check_budget("comp-1", 30)
    assert ok is False


async def test_check_budget_unlimited(svc: GovernanceService) -> None:
    await svc.create_budget_policy(
        BudgetPolicy(company_id="comp-1", name="test", monthly_limit=0)
    )
    ok = await svc.check_budget("comp-1", 999999999)
    assert ok is True


# ── UsageRecord ──


async def test_record_usage(svc: GovernanceService) -> None:
    record = UsageRecord(
        company_id="comp-1",
        provider_id="openai",
        model="gpt-4",
        input_tokens=1000,
        output_tokens=500,
        cost_micros=3000,
    )
    await svc.record_usage(record)
    assert record.record_id.startswith("ur-")


async def test_get_usage_summary(svc: GovernanceService) -> None:
    for i in range(3):
        await svc.record_usage(
            UsageRecord(
                company_id="comp-1",
                provider_id="openai",
                model="gpt-4",
                input_tokens=100 * (i + 1),
                output_tokens=50 * (i + 1),
                cost_micros=100 * (i + 1),
            )
        )
    summary = await svc.get_usage_summary("comp-1", "month")
    assert summary["record_count"] == 3
    assert summary["total_input_tokens"] == 600
    assert summary["total_output_tokens"] == 300
    assert summary["total_cost_micros"] == 600


async def test_get_usage_summary_empty(svc: GovernanceService) -> None:
    summary = await svc.get_usage_summary("comp-empty", "month")
    assert summary["record_count"] == 0


# ── Approval ──


async def test_create_approval(svc: GovernanceService) -> None:
    approval = Approval(
        company_id="comp-1",
        task_id="task-1",
        employee_id="emp-1",
        approval_type="budget_override",
        requested_by="emp-1",
    )
    created = await svc.create_approval(approval)
    assert created.approval_id.startswith("ap-")
    assert created.status == "pending"


async def test_approve(svc: GovernanceService) -> None:
    approval = await svc.create_approval(
        Approval(
            company_id="comp-1",
            employee_id="emp-1",
            approval_type="budget_override",
            requested_by="emp-1",
        )
    )
    result = await svc.approve(approval.approval_id, "manager-1", 1)
    assert result.status == "approved"
    assert result.approved_by == "manager-1"
    assert result.version == 2


async def test_reject(svc: GovernanceService) -> None:
    approval = await svc.create_approval(
        Approval(
            company_id="comp-1",
            employee_id="emp-1",
            approval_type="budget_override",
            requested_by="emp-1",
        )
    )
    result = await svc.reject(approval.approval_id, "manager-1", 1, "too expensive")
    assert result.status == "rejected"
    assert result.reason == "too expensive"


async def test_approve_version_conflict(svc: GovernanceService) -> None:
    approval = await svc.create_approval(
        Approval(
            company_id="comp-1",
            employee_id="emp-1",
            approval_type="budget_override",
            requested_by="emp-1",
        )
    )
    await svc.approve(approval.approval_id, "manager-1", 1)
    with pytest.raises(ValueError, match="not found or version mismatch"):
        await svc.approve(approval.approval_id, "manager-2", 1)
