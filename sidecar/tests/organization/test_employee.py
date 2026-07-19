"""员工测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.capability.models import Capability, PromptAsset, Skill
from acos.capability.prompt_service import PromptAssetService
from acos.capability.skill_service import SkillService
from acos.capability.service import CapabilityService
from acos.capability.versioning import VersioningService
from acos.organization.models import EmployeeTemplate, Employee
from acos.organization.service import OrganizationService
from acos.organization.template_service import TemplateService
from acos.organization.employee_service import EmployeeService
from acos.rpc.errors import AcosError
from acos.store.migrator import Migrator


async def _publish_prompt_asset(prompt_svc: PromptAssetService, versioning: VersioningService, company_id: str, name: str) -> tuple[str, int]:
    """创建并发布一个 PromptAsset，返回 (prompt_asset_id, version)"""
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
    """创建并发布一个 Skill，返回 skill_id"""
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
    """创建并发布一个 Capability，返回 capability_id"""
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
async def setup(tmp_path: Path) -> tuple[EmployeeService, str, str]:
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
    return EmployeeService(str(db_path)), company.company_id, template.template_id


async def test_create_employee(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id,
        department_id="dept-1",
        template_id=template_id,
        name="张三",
    )
    assert emp.employee_id
    assert emp.name == "张三"
    assert emp.status == "created"
    assert emp.version == 1
    assert emp.company_id == company_id


async def test_get_employee(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id, department_id="dept-1",
        template_id=template_id, name="李四",
    )
    fetched = await svc.get(emp.employee_id)
    assert fetched is not None
    assert fetched.name == "李四"


async def test_get_nonexistent_employee(setup: tuple[EmployeeService, str, str]) -> None:
    svc, _, _ = setup
    result = await svc.get("nonexistent")
    assert result is None


async def test_activate_employee(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id, department_id="dept-1",
        template_id=template_id, name="王五",
    )
    activated = await svc.activate(emp.employee_id, company_id, expected_version=1)
    assert activated.status == "active"
    assert activated.version == 2


async def test_suspend_employee(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id, department_id="dept-1",
        template_id=template_id, name="赵六",
    )
    await svc.activate(emp.employee_id, company_id, expected_version=1)
    suspended = await svc.suspend(emp.employee_id, company_id, expected_version=2)
    assert suspended.status == "suspended"


async def test_resume_employee(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id, department_id="dept-1",
        template_id=template_id, name="孙七",
    )
    await svc.activate(emp.employee_id, company_id, expected_version=1)
    await svc.suspend(emp.employee_id, company_id, expected_version=2)
    resumed = await svc.resume(emp.employee_id, company_id, expected_version=3)
    assert resumed.status == "active"


async def test_archive_employee(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id, department_id="dept-1",
        template_id=template_id, name="周八",
    )
    await svc.activate(emp.employee_id, company_id, expected_version=1)
    archived = await svc.archive(emp.employee_id, company_id, expected_version=2)
    assert archived.status == "archived"


async def test_invalid_transition(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id, department_id="dept-1",
        template_id=template_id, name="测试",
    )
    with pytest.raises(AcosError) as exc_info:
        await svc.archive(emp.employee_id, company_id, expected_version=1)
    assert exc_info.value.code == "ORG-STATE-INVALID"


async def test_update_employee_cas(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id, department_id="dept-1",
        template_id=template_id, name="原名",
    )
    updated = await svc.update(
        emp.employee_id, company_id, expected_version=1,
        updates={"name": "新名", "role_name": "高级开发者"},
    )
    assert updated.name == "新名"
    assert updated.role_name == "高级开发者"
    assert updated.version == 2


async def test_update_cas_conflict(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id, department_id="dept-1",
        template_id=template_id, name="原名",
    )
    await svc.update(emp.employee_id, company_id, expected_version=1, updates={"name": "A"})
    with pytest.raises(AcosError) as exc_info:
        await svc.update(emp.employee_id, company_id, expected_version=1, updates={"name": "B"})
    assert exc_info.value.code == "SYS-OPTIMISTIC-LOCK-CONFLICT"


async def test_list_by_company(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    await svc.create(company_id=company_id, department_id="d1", template_id=template_id, name="A")
    await svc.create(company_id=company_id, department_id="d2", template_id=template_id, name="B")
    emps = await svc.list_by_company(company_id)
    # activate_company 会创建 founder，加上手动创建的 2 人 = 3
    assert len(emps) == 3


async def test_list_by_department(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    await svc.create(company_id=company_id, department_id="d1", template_id=template_id, name="A")
    await svc.create(company_id=company_id, department_id="d1", template_id=template_id, name="B")
    await svc.create(company_id=company_id, department_id="d2", template_id=template_id, name="C")
    emps = await svc.list_by_department(company_id, "d1")
    assert len(emps) == 2


async def test_suspend_from_created_fails(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id, department_id="d1", template_id=template_id, name="X",
    )
    with pytest.raises(AcosError):
        await svc.suspend(emp.employee_id, company_id, expected_version=1)
