"""CompanyPlan generation — CEO/General Manager analyzes company info and department structures."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def generate_company_plan(
    db: Any,
    *,
    company_id: str,
    company_name: str,
    industry: str,
    introduction: str,
    general_manager_office: str,
    departments: list[dict[str, Any]],
    company_task_id: str,
    generated_by_run_id: str,
) -> dict[str, Any]:
    """Generate a CompanyPlan based on company info and department structures.

    The plan contains:
    1. Company vision and goals
    2. Department-level task breakdown
    3. Cross-department dependencies
    4. Quality gates
    """
    plan_id = _id()
    now = _now()

    sections: list[dict[str, Any]] = []

    # Section 1: Company Overview
    sections.append({
        "type": "company_overview",
        "title": f"{company_name} 运营计划",
        "description": f"基于{industry}行业的公司运营计划",
        "goals": [introduction[:200]],
    })

    # Section 2: Department Tasks
    for dept in departments:
        dept_section: dict[str, Any] = {
            "type": "department_tasks",
            "department_id": dept.get("id", ""),
            "department_name": dept.get("name", ""),
            "responsibilities": dept.get("responsibilities", []),
            "planned_tasks": [],
        }

        for resp in dept.get("responsibilities", []):
            task = {
                "task_id": _id(),
                "title": resp.get("title", ""),
                "description": resp.get("description", ""),
                "estimated_effort": "medium",
                "priority": "normal",
            }
            dept_section["planned_tasks"].append(task)

        sections.append(dept_section)

    # Section 3: Cross-department dependencies
    sections.append({
        "type": "dependencies",
        "cross_department": [],
        "quality_gates": [
            {"gate": "code_review", "description": "所有代码变更需经过审查"},
            {"gate": "test_pass", "description": "所有测试必须通过"},
        ],
    })

    canonical_json = json.dumps(sections, ensure_ascii=False, sort_keys=True)
    content_sha256 = hashlib.sha256(canonical_json.encode()).hexdigest()

    version_id = _id()
    await db.execute(
        """INSERT INTO company_plan_versions
           (id, company_task_id, company_id, version_number, canonical_json,
            content_sha256, generated_by_run_id, status, created_at)
           VALUES (?, ?, ?, 1, ?, ?, ?, 'draft', ?)""",
        (
            version_id,
            company_task_id,
            company_id,
            canonical_json,
            content_sha256,
            generated_by_run_id,
            now,
        ),
    )
    return {
        "plan_id": plan_id,
        "version_id": version_id,
        "company_id": company_id,
        "title": f"{company_name} 运营计划",
        "goals": [introduction[:200]],
        "non_goals": [],
        "final_acceptance_criteria": [],
        "department_tasks": [],
        "estimated_duration_hours": 0,
        "risk_assessment": "",
        "sections": sections,
        "status": "draft",
        "created_at": now,
    }
