"""公司解散协调器 + 消费者测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.organization.dissolution import (
    DissolutionOrchestrator,
    dissolution_backend_consumer,
    dissolution_knowledge_consumer,
    dissolution_organization_consumer,
    dissolution_provider_consumer,
    dissolution_task_consumer,
)
from acos.organization.service import OrganizationService
from acos.store.migrator import Migrator


@pytest.fixture
async def db_path(tmp_path: Path) -> str:
    path = tmp_path / "test.db"
    migrator = Migrator(str(path))
    await migrator.run_pending_migrations(
        str(Path(__file__).resolve().parents[2] / "migrations")
    )
    return str(path)


@pytest.fixture
async def active_company(db_path: str) -> tuple[str, str]:
    """创建并激活一个公司，返回 (company_id, owner_id)。"""
    svc = OrganizationService(db_path)
    company = await svc.create_company("解散测试公司", "owner-1")
    activated = await svc.activate_company(company.company_id, expected_version=1)
    return activated.company_id, "owner-1"


@pytest.fixture
def orchestrator(db_path: str) -> DissolutionOrchestrator:
    return DissolutionOrchestrator(db_path)


async def test_start_dissolution_initializes_watermarks(
    db_path: str, active_company: tuple[str, str], orchestrator: DissolutionOrchestrator
) -> None:
    company_id, owner_id = active_company
    svc = OrganizationService(db_path)

    await svc.start_dissolution(company_id, expected_version=2, operator=owner_id)

    check = await orchestrator.check_all_consumers_completed(company_id)
    assert check["completed"] is False
    assert set(check["pending"]) == {
        "organization", "task", "session", "knowledge", "provider", "backend"
    }


async def test_organization_consumer(
    db_path: str, active_company: tuple[str, str], orchestrator: DissolutionOrchestrator
) -> None:
    company_id, owner_id = active_company
    import aiosqlite

    # 先创建部门和员工以便验证
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """INSERT INTO departments
               (department_id, company_id, parent_department_id, name,
                leader_employee_id, status, created_at, updated_at, version)
               VALUES (?, ?, NULL, '测试部门', 'emp-leader', 'active', '', '', 1)""",
            ("dept-1", company_id),
        )
        await db.execute(
            """INSERT INTO employees
               (employee_id, company_id, department_id, template_id,
                capability_snapshot, name, role_name, employee_type,
                reports_to_employee_id, stability_level, status,
                session_transfer_state, primary_session_thread_id,
                version, created_at, updated_at)
               VALUES (?, ?, 'dept-1', '', '{}', '测试员工', '员工', 'department_leader',
                       NULL, 5, 'active', 'none', NULL, 1, '', '')""",
            ("emp-leader", company_id),
        )
        await db.commit()

    await dissolution_organization_consumer(db_path, company_id)
    await orchestrator.mark_consumer_completed(company_id, "organization")

    check = await orchestrator.check_all_consumers_completed(company_id)
    assert "organization" not in check["pending"]

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT leader_employee_id FROM departments WHERE department_id = 'dept-1'"
        )
        dept = await cur.fetchone()
        assert dept["leader_employee_id"] is None

        cur = await db.execute(
            "SELECT employee_type, status FROM employees WHERE employee_id = 'emp-leader'"
        )
        emp = await cur.fetchone()
        assert emp["employee_type"] == "employee"
        assert emp["status"] == "archived"


async def test_task_consumer(
    db_path: str, active_company: tuple[str, str], orchestrator: DissolutionOrchestrator
) -> None:
    company_id, _ = active_company
    import aiosqlite
    import uuid

    task_id = str(uuid.uuid4())
    node_id = str(uuid.uuid4())
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO tasks
               (task_id, company_id, title, status, version, created_at, updated_at)
               VALUES (?, ?, '测试任务', 'running', 1, '', '')""",
            (task_id, company_id),
        )
        await db.execute(
            """INSERT INTO task_nodes
               (node_id, task_id, company_id, status, version, created_at, updated_at)
               VALUES (?, ?, ?, 'running', 1, '', '')""",
            (node_id, task_id, company_id),
        )
        await db.commit()

    await dissolution_task_consumer(db_path, company_id)
    await orchestrator.mark_consumer_completed(company_id, "task")

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT status FROM task_nodes WHERE node_id = ?", (node_id,)
        )
        node = await cur.fetchone()
        assert node["status"] == "cancelled"


async def test_knowledge_consumer(
    db_path: str, active_company: tuple[str, str], orchestrator: DissolutionOrchestrator
) -> None:
    company_id, _ = active_company
    import aiosqlite

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT policy_id FROM knowledge_policies WHERE company_id = ?",
            (company_id,),
        )
        policy = await cur.fetchone()
        assert policy is not None
        policy_id = policy["policy_id"]

    await dissolution_knowledge_consumer(db_path, company_id)
    await orchestrator.mark_consumer_completed(company_id, "knowledge")

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT status FROM knowledge_policies WHERE policy_id = ?",
            (policy_id,),
        )
        row = await cur.fetchone()
        assert row["status"] == "frozen"


async def test_provider_consumer(
    db_path: str, active_company: tuple[str, str], orchestrator: DissolutionOrchestrator
) -> None:
    company_id, _ = active_company
    import aiosqlite

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO provider_availability
               (company_id, provider_id, available, healthy, reason, probed_at, version)
               VALUES (?, 'openai', 1, 1, 'ok', '', 1)""",
            (company_id,),
        )
        await db.commit()

    await dissolution_provider_consumer(db_path, company_id)
    await orchestrator.mark_consumer_completed(company_id, "provider")

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT available, reason FROM provider_availability WHERE company_id = ?",
            (company_id,),
        )
        row = await cur.fetchone()
        assert row["available"] == 0
        assert row["reason"] == "frozen_by_dissolution"


async def test_backend_consumer(
    db_path: str, active_company: tuple[str, str], orchestrator: DissolutionOrchestrator
) -> None:
    company_id, _ = active_company
    import aiosqlite
    import uuid

    backend_id = str(uuid.uuid4())
    lease_id = str(uuid.uuid4())
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO backends
               (backend_id, company_id, name, status, version, created_at, updated_at)
               VALUES (?, ?, 'test-backend', 'active', 1, '', '')""",
            (backend_id, company_id),
        )
        await db.execute(
            """INSERT INTO backend_leases
               (lease_id, backend_id, company_id, run_id, status, version, created_at, updated_at)
               VALUES (?, ?, ?, 'run-1', 'active', 1, '', '')""",
            (lease_id, backend_id, company_id),
        )
        await db.commit()

    await dissolution_backend_consumer(db_path, company_id)
    await orchestrator.mark_consumer_completed(company_id, "backend")

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT status FROM backend_leases WHERE lease_id = ?", (lease_id,)
        )
        lease = await cur.fetchone()
        assert lease["status"] == "released"

        cur = await db.execute(
            "SELECT status FROM backends WHERE backend_id = ?", (backend_id,)
        )
        backend = await cur.fetchone()
        assert backend["status"] == "disabled"


async def test_check_all_consumers_completed(
    db_path: str, active_company: tuple[str, str], orchestrator: DissolutionOrchestrator
) -> None:
    company_id, _ = active_company

    check = await orchestrator.check_all_consumers_completed(company_id)
    assert check["completed"] is False
    assert len(check["pending"]) == 6

    for consumer in ["organization", "task", "session", "knowledge", "provider", "backend"]:
        await orchestrator.mark_consumer_completed(company_id, consumer)

    check = await orchestrator.check_all_consumers_completed(company_id)
    assert check["completed"] is True
    assert check["pending"] == []


async def test_try_complete_dissolution_pending(
    db_path: str, active_company: tuple[str, str], orchestrator: DissolutionOrchestrator
) -> None:
    company_id, _ = active_company

    await orchestrator.mark_consumer_completed(company_id, "organization")
    result = await orchestrator.try_complete_dissolution(company_id)
    assert result["status"] == "pending"
    assert "organization" not in result["pending_consumers"]
    assert len(result["pending_consumers"]) == 5


async def test_try_complete_dissolution_dissolved(
    db_path: str, active_company: tuple[str, str], orchestrator: DissolutionOrchestrator
) -> None:
    company_id, _ = active_company
    svc = OrganizationService(db_path)

    await svc.start_dissolution(company_id, expected_version=2, operator="owner-1")

    for consumer in DissolutionOrchestrator.CONSUMERS:
        await orchestrator.mark_consumer_completed(company_id, consumer)

    result = await orchestrator.try_complete_dissolution(company_id)
    assert result["status"] == "dissolved"

    company = await svc.get_company(company_id)
    assert company is not None
    assert company.status == "dissolved"


async def test_create_intervention_for_failure(
    db_path: str, active_company: tuple[str, str], orchestrator: DissolutionOrchestrator
) -> None:
    company_id, _ = active_company
    import uuid

    trace_id = str(uuid.uuid4())
    intervention_id = await orchestrator.create_intervention_for_failure(
        company_id, ["task", "backend"], trace_id
    )
    assert intervention_id

    from acos.interventions.repository import InterventionRepository
    import aiosqlite

    repo = InterventionRepository()
    async with aiosqlite.connect(db_path) as db:
        intervention = await repo.get(db, intervention_id, company_id)
        assert intervention is not None
        assert intervention.subtype == "company_dissolution"
        assert intervention.status == "open"
        assert "retry" in intervention.allowed_actions


async def test_mark_consumer_completed_idempotent(
    db_path: str, active_company: tuple[str, str], orchestrator: DissolutionOrchestrator
) -> None:
    company_id, _ = active_company
    import aiosqlite

    await orchestrator.mark_consumer_completed(company_id, "task")
    await orchestrator.mark_consumer_completed(company_id, "task")

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT COUNT(*) as cnt FROM dissolution_watermarks "
            "WHERE company_id = ? AND consumer_name = 'task'",
            (company_id,),
        )
        row = await cur.fetchone()
        assert row["cnt"] == 1
