"""Transaction injection tests for atomic confirm_and_dispatch."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from ibreeze.orchestration.confirm_plan import ConfirmPlanCommand, confirm_and_dispatch


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


@pytest.fixture
async def env(db: Any) -> dict[str, str]:
    """Set up a minimal company with one department, one employee, and a draft plan."""
    now = _now()
    company_id = _id()
    revision_id = _id()
    dept_id = _id()
    dept_rev_id = _id()
    employee_id = _id()
    conv_id = _id()
    dept_conv_id = _id()
    profile_id = _id()
    version_id = _id()
    release_id = _id()

    await db.execute("PRAGMA foreign_keys = OFF")

    await db.execute(
        "INSERT INTO company_revisions"
        " (id, company_id, revision_number, name, introduction,"
        " content_sha256, created_by_type, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (revision_id, company_id, 1, "TestCo", "Test company", _sha256("test"), "system", now),
    )
    await db.execute(
        "INSERT INTO catalog_cache_releases"
        " (release_id, release_sequence, manifest_json, manifest_sha256,"
        " signature, signing_key_id, status, downloaded_at, activated_at)"
        " VALUES (?,1,'{}',?, 'sig', 'k1', 'active', ?, ?)",
        (release_id, _sha256("{}"), now, now),
    )
    await db.execute(
        "INSERT INTO employee_base_profiles"
        " (id, company_id, name, normalized_name, description,"
        " current_version_id, status, created_at, updated_at, version)"
        " VALUES (?,?,'Default','default','Default profile',?,'active',?,?,1)",
        (profile_id, company_id, version_id, now, now),
    )
    binding_json = json.dumps({"agent_cli": "/usr/bin/fake-cli"})
    await db.execute(
        "INSERT INTO employee_base_profile_versions"
        " (id, profile_id, version_number, name, description, profile_type,"
        " runtime_binding_json, system_prompt, capability_tags_json,"
        " tool_policy_json, timeout_seconds, max_retries, workspace_policy,"
        " catalog_release_id, content_sha256, status, created_at,"
        " published_at)"
        " VALUES (?,?,1,'Default v1','Default profile','agent_cli',?,"
        " 'Act carefully.','[]','{}',300,2,'workspace_rw_external_ro',?,?,"
        " 'published',?,?)",
        (version_id, profile_id, binding_json, release_id, _sha256("default"), now, now),
    )
    await db.execute(
        "INSERT INTO department_revisions"
        " (id, department_id, company_id, revision_number, name,"
        " function_description, content_sha256, created_at)"
        " VALUES (?,?,?,1,'Eng','Engineering dept',?,?)",
        (dept_rev_id, dept_id, company_id, _sha256("eng"), now),
    )
    await db.execute(
        "INSERT INTO conversations"
        " (id, company_id, conversation_type, status, created_at)"
        " VALUES (?,?,'department','active',?)",
        (dept_conv_id, company_id, now),
    )
    await db.execute(
        "INSERT INTO departments"
        " (id, company_id, department_type, normalized_name,"
        " current_revision_id, leader_employee_id,"
        " department_conversation_id, status, created_at, updated_at,"
        " version) VALUES (?,?,'standard','engineering',?,?,?,'active',?,?,1)",
        (dept_id, company_id, dept_rev_id, employee_id, dept_conv_id, now, now),
    )
    await db.execute(
        "INSERT INTO employees"
        " (id, company_id, department_id, display_name,"
        " normalized_display_name, base_profile_version_id, workflow_role,"
        " status, created_at, updated_at, version)"
        " VALUES (?,?,?,'Alice','alice',?,'member','active',?,?,1)",
        (employee_id, company_id, dept_id, version_id, now, now),
    )
    await db.execute(
        "INSERT INTO conversations"
        " (id, company_id, conversation_type, status, created_at)"
        " VALUES (?,?,'company','active',?)",
        (conv_id, company_id, now),
    )
    await db.execute(
        "INSERT INTO companies"
        " (id, normalized_name, current_revision_id,"
        " general_manager_office_id, general_manager_employee_id,"
        " company_conversation_id, status, created_at, updated_at, version)"
        " VALUES (?,?,?,?,?,?,'active',?,?,1)",
        (company_id, "testco", revision_id, dept_id, employee_id, conv_id, now, now),
    )
    task_id = _id()
    await db.execute(
        "INSERT INTO company_tasks"
        " (id, company_id, title, company_conversation_id,"
        " user_message_event_id, status, created_at, updated_at, version)"
        " VALUES (?,?,?,?,?,'awaiting_user_confirmation',?,?,1)",
        (task_id, company_id, "Build feature", conv_id, _id(), now, now),
    )

    plan_body = json.dumps({
        "company_id": company_id,
        "company_task_id": task_id,
        "plan_version": 1,
        "goal": "Implement login feature",
        "department_tasks": [
            {
                "department_id": dept_id,
                "local_ref": "fe-1",
                "objective": "Build login UI",
                "deliverables": [
                    {
                        "title": "Login page",
                        "description": "Login page component",
                        "contributor_employee_ids": [employee_id],
                    }
                ],
                "acceptance_criteria": ["Works in browser"],
                "dependency_refs": [],
            }
        ],
        "created_at": now,
    })
    plan_sha256 = _sha256(plan_body)
    plan_version_id = _id()
    await db.execute(
        "INSERT INTO company_plan_versions"
        " (id, company_task_id, company_id, version_number, canonical_json,"
        " content_sha256, generated_by_run_id, status, created_at)"
        " VALUES (?,?,?,1,?,?,?,?,?)",
        (plan_version_id, task_id, company_id, plan_body, plan_sha256, _id(), "awaiting_user_confirmation", now),
    )

    await db.execute("PRAGMA foreign_keys = ON")

    return {
        "company_id": company_id,
        "dept_id": dept_id,
        "employee_id": employee_id,
        "task_id": task_id,
        "plan_version_id": plan_version_id,
        "plan_sha256": plan_sha256,
        "conv_id": conv_id,
    }


class TestConfirmAndDispatch:
    """Test atomic confirm_and_dispatch transaction boundary."""

    @pytest.mark.asyncio
    async def test_happy_path(self, db: Any, env: dict[str, str]) -> None:
        plan_artifact_id = _id()
        command = ConfirmPlanCommand(
            company_id=env["company_id"],
            company_task_id=env["task_id"],
            plan_artifact_id=plan_artifact_id,
            plan_sha256=env["plan_sha256"],
            expected_version=1,
        )
        result = await confirm_and_dispatch(db, command)
        assert result["status"] == "confirmed"
        assert result["company_task_version"] == 2

        cursor = await db.execute(
            "SELECT status, version FROM company_tasks WHERE id=? AND company_id=?",
            (env["task_id"], env["company_id"]),
        )
        task = await cursor.fetchone()
        assert task["status"] == "executing"
        assert task["version"] == 2

        cursor = await db.execute(
            "SELECT id FROM department_tasks WHERE company_task_id=? AND company_id=?",
            (env["task_id"], env["company_id"]),
        )
        rows = await cursor.fetchall()
        assert len(rows) == 1

        cursor = await db.execute(
            "SELECT id FROM employee_tasks WHERE company_id=?",
            (env["company_id"],),
        )
        rows = await cursor.fetchall()
        assert len(rows) == 1

        cursor = await db.execute(
            "SELECT id FROM artifacts WHERE id=? AND company_id=?",
            (plan_artifact_id, env["company_id"]),
        )
        row = await cursor.fetchone()
        assert row is not None

        cursor = await db.execute(
            "SELECT id FROM agent_runs WHERE company_task_id=? AND company_id=?",
            (env["task_id"], env["company_id"]),
        )
        rows = await cursor.fetchall()
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_invalid_status(self, db: Any, env: dict[str, str]) -> None:
        await db.execute(
            "UPDATE company_tasks SET status='approved' WHERE id=?",
            (env["task_id"],),
        )
        command = ConfirmPlanCommand(
            company_id=env["company_id"],
            company_task_id=env["task_id"],
            plan_artifact_id=_id(),
            plan_sha256=env["plan_sha256"],
            expected_version=1,
        )
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await confirm_and_dispatch(db, command)

    @pytest.mark.asyncio
    async def test_sha256_mismatch(self, db: Any, env: dict[str, str]) -> None:
        command = ConfirmPlanCommand(
            company_id=env["company_id"],
            company_task_id=env["task_id"],
            plan_artifact_id=_id(),
            plan_sha256="a" * 64,
            expected_version=1,
        )
        with pytest.raises(ValueError, match="PLAN_SHA256_MISMATCH"):
            await confirm_and_dispatch(db, command)

    @pytest.mark.asyncio
    async def test_version_mismatch(self, db: Any, env: dict[str, str]) -> None:
        await db.execute(
            "UPDATE company_tasks SET version=5 WHERE id=?",
            (env["task_id"],),
        )
        command = ConfirmPlanCommand(
            company_id=env["company_id"],
            company_task_id=env["task_id"],
            plan_artifact_id=_id(),
            plan_sha256=env["plan_sha256"],
            expected_version=1,
        )
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await confirm_and_dispatch(db, command)

    @pytest.mark.asyncio
    async def test_already_executing(self, db: Any, env: dict[str, str]) -> None:
        await db.execute(
            "UPDATE company_tasks SET status='executing' WHERE id=?",
            (env["task_id"],),
        )
        command = ConfirmPlanCommand(
            company_id=env["company_id"],
            company_task_id=env["task_id"],
            plan_artifact_id=_id(),
            plan_sha256=env["plan_sha256"],
            expected_version=1,
        )
        result = await confirm_and_dispatch(db, command)
        assert result["status"] == "already_confirmed"

    @pytest.mark.asyncio
    async def test_resource_not_found(self, db: Any, env: dict[str, str]) -> None:
        command = ConfirmPlanCommand(
            company_id=env["company_id"],
            company_task_id="nonexistent-task",
            plan_artifact_id=_id(),
            plan_sha256=env["plan_sha256"],
            expected_version=1,
        )
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await confirm_and_dispatch(db, command)

    @pytest.mark.asyncio
    async def test_no_awaiting_plan(self, db: Any, env: dict[str, str]) -> None:
        await db.execute(
            "UPDATE company_plan_versions SET status='draft' WHERE company_task_id=?",
            (env["task_id"],),
        )
        command = ConfirmPlanCommand(
            company_id=env["company_id"],
            company_task_id=env["task_id"],
            plan_artifact_id=_id(),
            plan_sha256=env["plan_sha256"],
            expected_version=1,
        )
        with pytest.raises(ValueError, match="NO_AWAITING_PLAN"):
            await confirm_and_dispatch(db, command)

    @pytest.mark.asyncio
    async def test_catalog_auto_create(self, db: Any, env: dict[str, str]) -> None:
        await db.execute("DELETE FROM catalog_cache_releases")
        plan_artifact_id = _id()
        command = ConfirmPlanCommand(
            company_id=env["company_id"],
            company_task_id=env["task_id"],
            plan_artifact_id=plan_artifact_id,
            plan_sha256=env["plan_sha256"],
            expected_version=1,
        )
        result = await confirm_and_dispatch(db, command)
        assert result["status"] == "confirmed"

        cursor = await db.execute("SELECT release_id FROM catalog_cache_releases WHERE status='active'")
        row = await cursor.fetchone()
        assert row is not None
