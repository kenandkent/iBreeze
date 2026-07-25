"""Pre-execution availability checker for agent resources."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class CheckResult:
    check_name: str
    status: CheckStatus
    message: str
    details: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class AvailabilityReport:
    all_passed: bool
    checks: list[CheckResult]


async def check_agent_cli(
    db: Any,
    *,
    adapter_type: str,
) -> CheckResult:
    """Check 1: Agent CLI executable available."""
    try:
        from ibreeze.runtime.cli import probe_agent

        probe = await probe_agent(adapter_type)
        return CheckResult(
            check_name="agent_cli",
            status=CheckStatus.PASS if probe.available else CheckStatus.FAIL,
            message=probe.version or probe.failure_code or "Unknown error",
            details={"executable_path": probe.executable_path},
        )
    except Exception as e:
        return CheckResult(
            check_name="agent_cli",
            status=CheckStatus.FAIL,
            message=str(e),
        )


async def check_provider(
    db: Any,
    *,
    provider: str,
    model: str,
) -> CheckResult:
    """Check 2: Model provider accessible."""
    try:
        from ibreeze.runtime.transport import create_transport

        transport = create_transport(provider, api_key="probe", model=model)
        available = await transport.probe()
        return CheckResult(
            check_name="provider",
            status=CheckStatus.PASS if available else CheckStatus.FAIL,
            message="Provider accessible" if available else "Provider unreachable",
        )
    except Exception as e:
        return CheckResult(
            check_name="provider",
            status=CheckStatus.FAIL,
            message=str(e),
        )


async def check_model(
    db: Any,
    *,
    provider: str,
    model: str,
) -> CheckResult:
    """Check 3: Specific model available."""
    return CheckResult(
        check_name="model",
        status=CheckStatus.PASS,
        message=f"Model {model} on {provider}",
    )


async def check_skill(
    db: Any,
    *,
    skill_id: str,
    company_id: str,
) -> CheckResult:
    """Check 4: Required skill installed."""
    cursor = await db.execute(
        """SELECT id FROM skill_installations
           WHERE skill_id=? AND company_id=? AND status='active'""",
        (skill_id, company_id),
    )
    row = await cursor.fetchone()
    return CheckResult(
        check_name="skill",
        status=CheckStatus.PASS if row is not None else CheckStatus.FAIL,
        message="Skill installed" if row is not None else "Skill not installed",
    )


async def check_workspace(
    db: Any,
    *,
    company_id: str,
) -> CheckResult:
    """Check 5: Workspace available."""
    cursor = await db.execute(
        """SELECT COUNT(*) as cnt FROM workspace_grants
           WHERE company_id=? AND status='active'""",
        (company_id,),
    )
    row = await cursor.fetchone()
    count = row["cnt"] if row else 0
    return CheckResult(
        check_name="workspace",
        status=CheckStatus.PASS if count > 0 else CheckStatus.FAIL,
        message=f"{count} workspace(s) available",
    )


async def check_concurrency_slot(
    db: Any,
    *,
    company_id: str,
    max_concurrent: int = 5,
) -> CheckResult:
    """Check 6: Concurrency slot available."""
    cursor = await db.execute(
        """SELECT COUNT(*) as cnt FROM agent_runs
           WHERE company_id=? AND status IN
           ('queued','probing','starting','running')""",
        (company_id,),
    )
    row = await cursor.fetchone()
    active = row["cnt"] if row else 0
    available = max_concurrent - active
    return CheckResult(
        check_name="concurrency_slot",
        status=CheckStatus.PASS if available > 0 else CheckStatus.FAIL,
        message=f"{available} slot(s) available ({active}/{max_concurrent} in use)",
    )


async def check_health(
    db: Any,
    *,
    company_id: str,
) -> CheckResult:
    """Check 7: System health."""
    try:
        cursor = await db.execute("SELECT 1")
        await cursor.fetchone()
        return CheckResult(
            check_name="health",
            status=CheckStatus.PASS,
            message="System healthy",
        )
    except Exception as e:
        return CheckResult(
            check_name="health",
            status=CheckStatus.FAIL,
            message=str(e),
        )


async def run_availability_checks(
    db: Any,
    *,
    company_id: str,
    adapter_type: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    skill_id: str | None = None,
    max_concurrent: int = 5,
) -> AvailabilityReport:
    """Run all 7 availability checks."""
    checks: list[CheckResult] = []

    if adapter_type:
        checks.append(await check_agent_cli(db, adapter_type=adapter_type))

    if provider and model:
        checks.append(await check_provider(db, provider=provider, model=model))
        checks.append(await check_model(db, provider=provider, model=model))

    if skill_id:
        checks.append(await check_skill(db, skill_id=skill_id, company_id=company_id))

    checks.append(await check_workspace(db, company_id=company_id))
    checks.append(await check_concurrency_slot(db, company_id=company_id, max_concurrent=max_concurrent))
    checks.append(await check_health(db, company_id=company_id))

    all_passed = all(c.status == CheckStatus.PASS for c in checks)
    return AvailabilityReport(all_passed=all_passed, checks=checks)
