"""权限引擎测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.capability.models import Capability, PromptAsset, Skill
from acos.capability.prompt_service import PromptAssetService
from acos.capability.skill_service import SkillService
from acos.capability.service import CapabilityService
from acos.capability.versioning import VersioningService
from acos.organization.employee_service import EmployeeService
from acos.organization.permission_engine import PermissionEngine
from acos.organization.service import OrganizationService
from acos.organization.template_service import TemplateService
from acos.store.migrator import Migrator


async def _publish_prompt_asset(prompt_svc: PromptAssetService, versioning: VersioningService, company_id: str, name: str) -> tuple[str, int]:
    prompt = PromptAsset(
        company_scope="company",
        company_id=company_id,
        name=name,
        segments={
            "system": "你是助手",
            "developer": "",
            "user_template": "{{input}}",
            "tool_instructions": "",
            "output_contract": "",
        },
        variables=[],
        context_slots=[],
    )
    prompt = await prompt_svc.create(prompt)
    await versioning.submit_review("prompt_asset", prompt.prompt_asset_id, 1)
    await versioning.publish("prompt_asset", prompt.prompt_asset_id, 1)
    return prompt.prompt_asset_id, 1


async def _publish_skill(skill_svc: SkillService, versioning: VersioningService, company_id: str, prompt_asset_id: str, name: str) -> str:
    skill = Skill(
        company_scope="company",
        company_id=company_id,
        name=name,
        prompt_asset_id=prompt_asset_id,
        prompt_asset_version=1,
        tool_bindings=[],
        knowledge_refs=[],
        input_schema={},
        output_schema={},
    )
    skill = await skill_svc.create(skill)
    await versioning.submit_review("skill", skill.skill_id, 1)
    await versioning.publish("skill", skill.skill_id, 1)
    return skill.skill_id


async def _publish_capability(cap_svc: CapabilityService, versioning: VersioningService, company_id: str, skill_id: str, name: str) -> str:
    import aiosqlite
    async with aiosqlite.connect(cap_svc._db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT checksum FROM skills WHERE skill_id = ?",
            (skill_id,),
        )
        skill_row = await cursor.fetchone()
        skill_checksum = skill_row["checksum"] if skill_row else ""

    cap = Capability(
        company_id=company_id,
        name=name,
        description=f"{name} 描述",
        source_category="code",
        visibility="company",
        cost_policy={"stability_level": 5},
    )
    cap = await cap_svc.create(
        cap,
        bindings=[{"skill_id": skill_id, "skill_version": 1, "skill_version_checksum": skill_checksum}],
    )
    await versioning.submit_review("capability", cap.capability_id, 1)
    await versioning.publish("capability", cap.capability_id, 1)
    return cap.capability_id


@pytest.fixture
async def setup(tmp_path: Path) -> tuple[PermissionEngine, EmployeeService, str, str]:
    db_path = tmp_path / "test.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(str(Path(__file__).resolve().parents[2] / "migrations"))
    org_svc = OrganizationService(str(db_path))
    company = await org_svc.create_company("测试公司", "owner-1")
    await org_svc.activate_company(company.company_id, expected_version=1)

    # 创建完整的 capability 链
    prompt_svc = PromptAssetService(str(db_path))
    skill_svc = SkillService(str(db_path))
    cap_svc = CapabilityService(str(db_path))
    versioning = VersioningService(str(db_path))

    prompt_asset_id, _ = await _publish_prompt_asset(prompt_svc, versioning, company.company_id, "测试Prompt")
    skill_id = await _publish_skill(skill_svc, versioning, company.company_id, prompt_asset_id, "测试Skill")
    capability_id = await _publish_capability(cap_svc, versioning, company.company_id, skill_id, "测试能力")

    template_svc = TemplateService(str(db_path))
    template = await template_svc.create(
        company_id=company.company_id,
        capability_id=capability_id,
        capability_version=1,
        default_role="开发者",
    )
    await template_svc.activate(template.template_id, company.company_id, expected_version=1)
    emp_svc = EmployeeService(str(db_path))
    perm_engine = PermissionEngine(str(db_path))
    return perm_engine, emp_svc, company.company_id, template.template_id


async def test_compute_scope_empty(
    setup: tuple[PermissionEngine, EmployeeService, str, str],
) -> None:
    perm_engine, emp_svc, company_id, template_id = setup
    emp = await emp_svc.create(
        company_id=company_id, department_id="d1", template_id=template_id, name="A",
    )
    scope = await perm_engine.compute_scope(emp.employee_id, company_id)
    assert scope["granted_departments"] == []
    assert scope["granted_tasks"] == []
    assert "visible_department_ids" in scope
    assert "private_visible_employee_ids" in scope
    assert scope["scope_hash"]


async def test_grant_and_authorize(
    setup: tuple[PermissionEngine, EmployeeService, str, str],
) -> None:
    perm_engine, emp_svc, company_id, template_id = setup
    emp = await emp_svc.create(
        company_id=company_id, department_id="d1", template_id=template_id, name="A",
    )
    grant_id = await perm_engine.grant(
        company_id=company_id,
        employee_id=emp.employee_id,
        target_type="department",
        target_id="dept-001",
        permission="department_read",
        expires_at="2099-01-01T00:00:00Z",
        approved_by="owner-1",
    )
    assert grant_id

    authorized = await perm_engine.authorize(
        emp.employee_id, company_id, "department", "dept-001",
    )
    assert authorized["decision"] == "allow"


async def test_authorize_no_grant(
    setup: tuple[PermissionEngine, EmployeeService, str, str],
) -> None:
    perm_engine, emp_svc, company_id, template_id = setup
    emp = await emp_svc.create(
        company_id=company_id, department_id="d1", template_id=template_id, name="A",
    )
    authorized = await perm_engine.authorize(
        emp.employee_id, company_id, "department", "dept-001",
    )
    assert authorized["decision"] == "deny"


async def test_revoke_grant(
    setup: tuple[PermissionEngine, EmployeeService, str, str],
) -> None:
    perm_engine, emp_svc, company_id, template_id = setup
    emp = await emp_svc.create(
        company_id=company_id, department_id="d1", template_id=template_id, name="A",
    )
    grant_id = await perm_engine.grant(
        company_id=company_id, employee_id=emp.employee_id,
        target_type="task", target_id="task-001",
        permission="task_read", expires_at="2099-01-01T00:00:00Z",
        approved_by="owner-1",
    )
    revoked = await perm_engine.revoke(grant_id, company_id, expected_version=1)
    assert revoked is True

    authorized = await perm_engine.authorize(
        emp.employee_id, company_id, "task", "task-001",
    )
    assert authorized["decision"] == "deny"


async def test_scope_with_grants(
    setup: tuple[PermissionEngine, EmployeeService, str, str],
) -> None:
    perm_engine, emp_svc, company_id, template_id = setup
    emp = await emp_svc.create(
        company_id=company_id, department_id="d1", template_id=template_id, name="A",
    )
    await perm_engine.grant(
        company_id=company_id, employee_id=emp.employee_id,
        target_type="department", target_id="dept-1",
        permission="department_read", expires_at="2099-01-01T00:00:00Z",
        approved_by="owner-1",
    )
    await perm_engine.grant(
        company_id=company_id, employee_id=emp.employee_id,
        target_type="task", target_id="task-1",
        permission="task_read", expires_at="2099-01-01T00:00:00Z",
        approved_by="owner-1",
    )
    scope = await perm_engine.compute_scope(emp.employee_id, company_id)
    assert "dept-1" in scope["granted_departments"]
    assert "task-1" in scope["granted_tasks"]


async def test_authorize_task(
    setup: tuple[PermissionEngine, EmployeeService, str, str],
) -> None:
    perm_engine, emp_svc, company_id, template_id = setup
    emp = await emp_svc.create(
        company_id=company_id, department_id="d1", template_id=template_id, name="A",
    )
    await perm_engine.grant(
        company_id=company_id, employee_id=emp.employee_id,
        target_type="task", target_id="task-99",
        permission="task_read", expires_at="2099-01-01T00:00:00Z",
        approved_by="owner-1",
    )
    assert (await perm_engine.authorize(emp.employee_id, company_id, "task", "task-99"))["decision"] == "allow"
    assert (await perm_engine.authorize(emp.employee_id, company_id, "task", "task-100"))["decision"] == "deny"