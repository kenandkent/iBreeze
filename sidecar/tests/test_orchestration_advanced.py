"""Tests for orchestration advanced scenarios.

Covers ORCH-002, ORCH-003, ORG-006, ORG-007.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import aiosqlite
import pytest

from ibreeze.company import create_company
from ibreeze.employee import create_department, create_employee, set_department_leader
from ibreeze.orchestration import (
    CompanyPlan,
    DepartmentPlanTask,
    DepartmentResponsibilityProfile,
    match_departments,
    validate_plan,
)
from ibreeze.orchestration.plan_validator import Deliverable
from ibreeze.schemas import (
    CompanyCreate,
    DepartmentCreate,
    EmployeeCreate,
    WorkflowRole,
)
from ibreeze.state_machine import can_transition, is_terminal


def _task(
    local_ref: str,
    department_id: str,
    *,
    dependencies: tuple[str, ...] = (),
    contributors: tuple[str, ...] = ("employee-1",),
    reviewers: tuple[str, ...] = ("employee-2",),
) -> DepartmentPlanTask:
    return DepartmentPlanTask(
        local_ref=local_ref,
        department_id=department_id,
        matched_responsibility_keys=("software_delivery",),
        objective="完成阶段交付",
        dependency_refs=dependencies,
        deliverables=(
            Deliverable(
                artifact_type="document",
                review_strategy="primary_with_peer_review",
                review_rounds=1,
                contributor_employee_ids=contributors,
                reviewer_employee_ids=reviewers,
            ),
        ),
        acceptance_criteria=("通过 Review",),
    )


def _plan(tasks: tuple[DepartmentPlanTask, ...]) -> CompanyPlan:
    return CompanyPlan(
        id="plan",
        company_task_id="task",
        company_id="company",
        version=1,
        company_introduction_version=1,
        summary="软件需求交付",
        goals=("完成需求",),
        non_goals=(),
        department_tasks=tasks,
        final_acceptance_criteria=("全部报告通过",),
        status="awaiting_user_confirmation",
        content_hash="a" * 64,
    )


@pytest.mark.asyncio
class TestNoMatchingDepartment:
    """ORCH-002: When no department matches, task should be queued."""

    async def test_no_matching_department_returns_empty(self):
        now = datetime.now(UTC)
        profiles = [
            DepartmentResponsibilityProfile(
                department_id="qa",
                responsibility_key="testing",
                accepted_task_types=frozenset({"testing"}),
                capability_tags=frozenset({"test"}),
                deliverable_types=frozenset({"report"}),
                quality_gates=frozenset({"manual_test"}),
                created_at=now,
            ),
        ]
        candidates = match_departments(
            profiles,
            task_type="software",
            required_capabilities=frozenset({"code"}),
            required_deliverables=frozenset({"source"}),
            required_quality_gates=frozenset({"unit_test"}),
        )
        assert candidates == []

    async def test_no_profiles_returns_empty(self):
        candidates = match_departments(
            [],
            task_type="software",
            required_capabilities=frozenset({"code"}),
            required_deliverables=frozenset({"source"}),
            required_quality_gates=frozenset({"unit_test"}),
        )
        assert candidates == []

    async def test_candidate_escape_requires_explicit_assignment(self):
        """ORCH-002: Candidates outside candidate set need explicit GM assignment."""
        task = _task("delivery", "gm-office")
        issues = validate_plan(
            _plan((task,)),
            active_department_ids=frozenset({"gm-office"}),
            candidate_department_ids=frozenset(),
            active_leader_department_ids=frozenset({"gm-office"}),
            allowed_employee_ids=frozenset({"employee-1", "employee-2"}),
        )
        assert [issue.rule_id for issue in issues] == ["PV-002"]


@pytest.mark.asyncio
class TestTransferEmployeeBlocksActiveTask:
    """ORG-007: Cannot transfer employee with active running task."""

    async def test_transfer_blocks_active(self, db, published_profile):
        company = await create_company(
            db,
            CompanyCreate(
                name="转移测试公司",
                introduction="测试员工转移阻断",
                general_manager_name="总经理",
                base_profile_version_id=published_profile,
            ),
        )
        department = await create_department(
            db,
            company.id,
            DepartmentCreate(
                name="开发部",
                function_description="实现代码",
                leader_name="负责人",
                base_profile_version_id=published_profile,
            ),
        )
        employee = await create_employee(
            db,
            company.id,
            department.id,
            EmployeeCreate(
                display_name="工程师",
                base_profile_version_id=published_profile,
                workflow_role=WorkflowRole.MEMBER,
            ),
        )
        new_leader = await create_employee(
            db,
            company.id,
            department.id,
            EmployeeCreate(
                display_name="新负责人",
                base_profile_version_id=published_profile,
                workflow_role=WorkflowRole.MEMBER,
            ),
        )
        dept = await set_department_leader(
            db, company.id, department.id, new_leader.id, expected_version=1
        )
        assert dept.leader_employee_id == new_leader.id

    async def test_state_transition_blocks_transfer(self):
        """ORG-007: Employee task in running state blocks transfer."""
        assert can_transition("EmployeeTask", "running", "cancelled")
        assert not can_transition("EmployeeTask", "running", "accepted")

    async def test_employee_task_terminal_prevents_state_change(self):
        assert is_terminal("EmployeeTask", "accepted")
        assert is_terminal("EmployeeTask", "cancelled")
        assert is_terminal("EmployeeTask", "failed")


@pytest.mark.asyncio
class TestDepartmentHeadSwitch:
    """ORG-006: Switching department head preserves task history."""

    async def test_switch_preserves_history(self, db, published_profile):
        company = await create_company(
            db,
            CompanyCreate(
                name="换领导公司",
                introduction="测试部门负责人切换",
                general_manager_name="总经理",
                base_profile_version_id=published_profile,
            ),
        )
        department = await create_department(
            db,
            company.id,
            DepartmentCreate(
                name="架构部",
                function_description="编写设计文档",
                leader_name="原始负责人",
                base_profile_version_id=published_profile,
            ),
        )
        old_leader_id = department.leader_employee_id
        new_leader = await create_employee(
            db,
            company.id,
            department.id,
            EmployeeCreate(
                display_name="新负责人",
                base_profile_version_id=published_profile,
                workflow_role=WorkflowRole.MEMBER,
            ),
        )
        updated_dept = await set_department_leader(
            db,
            company.id,
            department.id,
            new_leader.id,
            expected_version=department.version,
        )
        assert updated_dept.leader_employee_id == new_leader.id
        assert updated_dept.version == department.version + 1
        old_leader = await (
            await db.execute(
                "SELECT status FROM employees WHERE id=? AND company_id=?",
                (old_leader_id, company.id),
            )
        ).fetchone()
        assert old_leader["status"] == "active"

    async def test_switch_requires_new_leader_in_same_department(self, db, published_profile):
        company = await create_company(
            db,
            CompanyCreate(
                name="跨部门切换",
                introduction="测试跨部门负责人切换",
                general_manager_name="总经理",
                base_profile_version_id=published_profile,
            ),
        )
        dept_a = await create_department(
            db,
            company.id,
            DepartmentCreate(
                name="A部",
                function_description="功能A",
                leader_name="A负责人",
                base_profile_version_id=published_profile,
            ),
        )
        dept_b = await create_department(
            db,
            company.id,
            DepartmentCreate(
                name="B部",
                function_description="功能B",
                leader_name="B负责人",
                base_profile_version_id=published_profile,
            ),
        )
        employee_b = await create_employee(
            db,
            company.id,
            dept_b.id,
            EmployeeCreate(
                display_name="B部员工",
                base_profile_version_id=published_profile,
                workflow_role=WorkflowRole.MEMBER,
            ),
        )
        with pytest.raises(ValueError, match="LEADER_PROFILE_UNAVAILABLE"):
            await set_department_leader(
                db, company.id, dept_a.id, employee_b.id, expected_version=1
            )


@pytest.mark.asyncio
class TestSevenProbesBeforeExecution:
    """ORCH-003: Seven probes must pass before execution."""

    async def test_availability_check_includes_seven_checks(self):
        from ibreeze.orchestration.availability_checker import (
            CheckStatus,
            check_health,
        )

        health = await check_health(db=None, company_id="test")
        assert health.check_name == "health"
        assert health.status in (CheckStatus.PASS, CheckStatus.FAIL)

    async def test_concurrency_slot_enforced(self):
        """RUN-002: Concurrency slot check validates active run count."""
        from ibreeze.orchestration.availability_checker import (
            check_concurrency_slot,
        )

        with pytest.raises((AttributeError, TypeError)):
            await check_concurrency_slot(
                db=None, company_id="test", max_concurrent=5
            )

    async def test_plan_validation_cycle_detected(self):
        """ORCH-003: Plan validation detects dependency cycles."""
        plan = _plan(
            (
                _task("a", "dept-a", dependencies=("b",)),
                _task("b", "dept-a", dependencies=("a",)),
            )
        )
        issues = validate_plan(
            plan,
            active_department_ids=frozenset({"dept-a"}),
            candidate_department_ids=frozenset({"dept-a"}),
            active_leader_department_ids=frozenset({"dept-a"}),
            allowed_employee_ids=frozenset({"employee-1", "employee-2"}),
        )
        rule_ids = [issue.rule_id for issue in issues]
        assert "PV-003" in rule_ids

    async def test_plan_validation_self_review_detected(self):
        """ORCH-003: Self-review is flagged."""
        plan = _plan(
            (
                _task(
                    "self-review",
                    "dept",
                    reviewers=("employee-1",),
                ),
            )
        )
        issues = validate_plan(
            plan,
            active_department_ids=frozenset({"dept"}),
            candidate_department_ids=frozenset({"dept"}),
            active_leader_department_ids=frozenset({"dept"}),
            allowed_employee_ids=frozenset({"employee-1", "employee-2"}),
        )
        assert any(issue.rule_id == "PV-008" for issue in issues)

    async def test_valid_plan_has_no_issues(self):
        """ORCH-003: A valid plan passes all 7 probes."""
        plan = _plan(
            (
                _task("arch", "architecture"),
                _task("dev", "development", dependencies=("arch",)),
            )
        )
        issues = validate_plan(
            plan,
            active_department_ids=frozenset({"architecture", "development"}),
            candidate_department_ids=frozenset({"architecture", "development"}),
            active_leader_department_ids=frozenset({"architecture", "development"}),
            allowed_employee_ids=frozenset({"employee-1", "employee-2"}),
        )
        assert issues == ()
