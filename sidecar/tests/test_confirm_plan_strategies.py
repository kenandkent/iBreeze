"""Collaboration strategy → execution graph assertions.

Four review strategies must map to the execution graph the same way every
time: independent_drafts/section_partition run every contributor in parallel;
primary_with_peer_review runs only the primary contributor and defers peers to
lazy review assignments; sequential_refinement chains contributors with
employee_task_dependencies and defers every segment after the first to
employee_task.graph_advance.  Reviewers never get an employee task.
"""

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


async def _insert_employee(
    db: Any,
    company_id: str,
    dept_id: str,
    profile_version_id: str,
    now: str,
    name: str,
) -> str:
    employee_id = _id()
    await db.execute(
        "INSERT INTO employees"
        " (id, company_id, department_id, display_name,"
        " normalized_display_name, base_profile_version_id, workflow_role,"
        " status, created_at, updated_at, version)"
        " VALUES (?,?,?,?,?,?,'member','active',?,?,1)",
        (employee_id, company_id, dept_id, name, name.lower(), profile_version_id, now, now),
    )
    return employee_id


@pytest.fixture
async def strategy_env(db: Any) -> dict[str, str]:
    """Company with one department and three active employees (alice/bob/carol)."""
    now = _now()
    company_id = _id()
    revision_id = _id()
    dept_id = _id()
    dept_rev_id = _id()
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
        " catalog_release_id, content_sha256, status, created_at, published_at)"
        " VALUES (?,?,1,'Default v1','Default profile','agent_cli',?,"
        " 'Act carefully.','[\"code\",\"review\"]','{}',300,2,'workspace_rw_external_ro',?,?,"
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
        "INSERT INTO conversations (id, company_id, conversation_type, status, created_at) VALUES (?,?,'department','active',?)",
        (dept_conv_id, company_id, now),
    )
    await db.execute(
        "INSERT INTO departments"
        " (id, company_id, department_type, normalized_name,"
        " current_revision_id, leader_employee_id, department_conversation_id,"
        " status, created_at, updated_at, version) VALUES (?,?,'standard','engineering',?,?,?,"
        " 'active',?,?,1)",
        (dept_id, company_id, dept_rev_id, _id(), dept_conv_id, now, now),
    )
    alice_id = await _insert_employee(db, company_id, dept_id, version_id, now, "Alice")
    bob_id = await _insert_employee(db, company_id, dept_id, version_id, now, "Bob")
    carol_id = await _insert_employee(db, company_id, dept_id, version_id, now, "Carol")
    await db.execute(
        "INSERT INTO conversations (id, company_id, conversation_type, status, created_at) VALUES (?,?,'company','active',?)",
        (conv_id, company_id, now),
    )
    await db.execute(
        "INSERT INTO companies"
        " (id, normalized_name, current_revision_id, general_manager_office_id,"
        " general_manager_employee_id, company_conversation_id, status,"
        " created_at, updated_at, version)"
        " VALUES (?,?,?,?,?,?,'active',?,?,1)",
        (company_id, "testco", revision_id, dept_id, alice_id, conv_id, now, now),
    )
    task_id = _id()
    await db.execute(
        "INSERT INTO company_tasks"
        " (id, company_id, title, company_conversation_id,"
        " user_message_event_id, status, created_at, updated_at, version)"
        " VALUES (?,?,?,?,?,'awaiting_user_confirmation',?,?,1)",
        (task_id, company_id, "Build feature", conv_id, _id(), now, now),
    )
    workspace_grant_id = _id()
    workspace_id = _id()
    await db.execute(
        "INSERT INTO workspace_grants"
        " (id, company_id, normalized_path, security_bookmark, path_type, status, created_at)"
        " VALUES (?,?,?,?,'code_repository','active',?)",
        (workspace_grant_id, company_id, f"/tmp/ibreeze-{workspace_grant_id}", b"test-bookmark", now),
    )
    await db.execute(
        "INSERT INTO task_workspaces"
        " (id, company_id, company_task_id, workspace_grant_id, repository_root,"
        " baseline_commit_sha, user_branch_name, integration_branch_name,"
        " integration_worktree_path, status, created_at, updated_at, version)"
        " VALUES (?,?,?,?,?,?,?,?,'/tmp/ibreeze-integration','active',?,?,1)",
        (
            workspace_id,
            company_id,
            task_id,
            workspace_grant_id,
            f"/tmp/ibreeze-{workspace_grant_id}",
            "a" * 40,
            "main",
            "ibreeze/integration",
            now,
            now,
        ),
    )

    await db.execute("PRAGMA foreign_keys = ON")

    return {
        "company_id": company_id,
        "dept_id": dept_id,
        "task_id": task_id,
        "alice_id": alice_id,
        "bob_id": bob_id,
        "carol_id": carol_id,
        "now": now,
    }


async def _register_plan(
    db: Any,
    env: dict[str, str],
    deliverables: list[dict[str, Any]],
    *,
    required_capability_tags: list[str] | None = None,
) -> str:
    plan_body = json.dumps(
        {
            "company_id": env["company_id"],
            "company_task_id": env["task_id"],
            "plan_version": 1,
            "goal": "Implement feature",
            "department_tasks": [
                {
                    "department_id": env["dept_id"],
                    "local_ref": "fe-1",
                    "objective": "Build feature",
                    "deliverables": deliverables,
                    "acceptance_criteria": ["Works"],
                    "dependency_refs": [],
                    "required_capability_tags": required_capability_tags or [],
                }
            ],
            "created_at": env["now"],
        }
    )
    plan_sha256 = _sha256(plan_body)
    await db.execute(
        "INSERT INTO company_plan_versions"
        " (id, company_task_id, company_id, version_number, canonical_json,"
        " content_sha256, generated_by_run_id, status, created_at)"
        " VALUES (?,?,?,1,?,?,?,?,?)",
        (_id(), env["task_id"], env["company_id"], plan_body, plan_sha256, _id(), "awaiting_user_confirmation", env["now"]),
    )
    return plan_sha256


async def _confirm(db: Any, env: dict[str, str], plan_sha256: str) -> dict[str, Any]:
    return await confirm_and_dispatch(
        db,
        ConfirmPlanCommand(
            company_id=env["company_id"],
            company_task_id=env["task_id"],
            plan_artifact_id=_id(),
            plan_sha256=plan_sha256,
            expected_version=1,
        ),
    )


def _deliverable(
    strategy: str,
    contributors: list[str],
    reviewers: list[str],
    artifact_type: str = "code",
    rounds: int = 2,
) -> dict[str, Any]:
    return {
        "title": "Deliverable",
        "description": "Thing",
        "artifact_type": artifact_type,
        "review_strategy": strategy,
        "review_rounds": rounds,
        "contributor_employee_ids": contributors,
        "reviewer_employee_ids": reviewers,
    }


async def _rows(db: Any, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    return await (await db.execute(sql, params)).fetchall()


class TestParallelStrategies:
    @pytest.mark.asyncio
    async def test_independent_drafts_runs_every_contributor(self, db: Any, strategy_env: dict[str, str]) -> None:
        env = strategy_env
        sha = await _register_plan(
            db,
            env,
            [_deliverable("independent_drafts", [env["alice_id"], env["bob_id"]], [env["carol_id"]])],
        )
        result = await _confirm(db, env, sha)
        assert result["status"] == "confirmed"

        emp = await _rows(db, "SELECT id, employee_id, status FROM employee_tasks WHERE company_id=?", (env["company_id"],))
        assert len(emp) == 2
        assert {row["employee_id"] for row in emp} == {env["alice_id"], env["bob_id"]}
        assert all(row["status"] == "assigned" for row in emp)
        # Every contributor task got a run immediately.
        runs = await _rows(
            db,
            "SELECT employee_task_id FROM agent_runs WHERE company_id=?",
            (env["company_id"],),
        )
        assert len(runs) == 2
        # Reviewer never gets an employee task.
        carol_tasks = [r for r in emp if r["employee_id"] == env["carol_id"]]
        assert carol_tasks == []
        # Frozen review spec written with full contributor + reviewer lists.
        spec = await _rows(
            db,
            "SELECT review_strategy, reviewer_employee_ids_json, contributor_employee_ids_json, review_rounds"
            " FROM deliverable_review_specs WHERE company_id=? AND company_task_id=?",
            (env["company_id"], env["task_id"]),
        )
        assert len(spec) == 1
        assert spec[0]["review_strategy"] == "independent_drafts"
        assert json.loads(spec[0]["contributor_employee_ids_json"]) == [env["alice_id"], env["bob_id"]]
        assert json.loads(spec[0]["reviewer_employee_ids_json"]) == [env["carol_id"]]
        assert spec[0]["review_rounds"] == 2

    @pytest.mark.asyncio
    async def test_section_partition_matches_independent(self, db: Any, strategy_env: dict[str, str]) -> None:
        env = strategy_env
        sha = await _register_plan(
            db,
            env,
            [_deliverable("section_partition", [env["alice_id"], env["bob_id"]], [env["carol_id"]])],
        )
        result = await _confirm(db, env, sha)
        assert result["status"] == "confirmed"
        emp = await _rows(db, "SELECT employee_id FROM employee_tasks WHERE company_id=?", (env["company_id"],))
        assert {row["employee_id"] for row in emp} == {env["alice_id"], env["bob_id"]}


class TestPrimaryWithPeerReview:
    @pytest.mark.asyncio
    async def test_only_primary_contributor_executes(self, db: Any, strategy_env: dict[str, str]) -> None:
        env = strategy_env
        sha = await _register_plan(
            db,
            env,
            [_deliverable("primary_with_peer_review", [env["alice_id"], env["bob_id"]], [env["carol_id"]])],
        )
        result = await _confirm(db, env, sha)
        assert result["status"] == "confirmed"

        emp = await _rows(db, "SELECT employee_id FROM employee_tasks WHERE company_id=?", (env["company_id"],))
        # Only the primary contributor produces.
        assert [row["employee_id"] for row in emp] == [env["alice_id"]]
        runs = await _rows(db, "SELECT employee_task_id FROM agent_runs WHERE company_id=?", (env["company_id"],))
        assert len(runs) == 1
        # Spec still freezes the full contributor set for reviewer checks.
        spec = await _rows(
            db,
            "SELECT review_strategy, contributor_employee_ids_json FROM deliverable_review_specs WHERE company_id=? AND company_task_id=?",
            (env["company_id"], env["task_id"]),
        )
        assert spec[0]["review_strategy"] == "primary_with_peer_review"
        assert json.loads(spec[0]["contributor_employee_ids_json"]) == [env["alice_id"], env["bob_id"]]


class TestCapabilityPreflight:
    @pytest.mark.asyncio
    async def test_missing_profile_capability_keeps_plan_waiting(self, db: Any, strategy_env: dict[str, str]) -> None:
        env = strategy_env
        sha = await _register_plan(
            db,
            env,
            [_deliverable("independent_drafts", [env["alice_id"]], [env["carol_id"]])],
            required_capability_tags=["security"],
        )
        result = await _confirm(db, env, sha)
        assert result["status"] == "waiting_resource"
        assert await _rows(db, "SELECT 1 FROM employee_tasks WHERE company_id=?", (env["company_id"],)) == []

    @pytest.mark.asyncio
    async def test_unavailable_reviewer_keeps_plan_waiting(self, db: Any, strategy_env: dict[str, str]) -> None:
        env = strategy_env
        await db.execute("UPDATE employees SET status='inactive' WHERE id=?", (env["carol_id"],))
        sha = await _register_plan(
            db,
            env,
            [_deliverable("independent_drafts", [env["alice_id"]], [env["carol_id"]])],
        )
        result = await _confirm(db, env, sha)
        assert result["status"] == "waiting_resource"
        assert await _rows(db, "SELECT 1 FROM employee_tasks WHERE company_id=?", (env["company_id"],)) == []


class TestSequentialRefinement:
    @pytest.mark.asyncio
    async def test_chained_graph_defers_later_segments(self, db: Any, strategy_env: dict[str, str]) -> None:
        env = strategy_env
        sha = await _register_plan(
            db,
            env,
            [_deliverable("sequential_refinement", [env["alice_id"], env["bob_id"]], [env["carol_id"]])],
            required_capability_tags=["code", "review"],
        )
        result = await _confirm(db, env, sha)
        assert result["status"] == "confirmed"

        emp = await _rows(
            db,
            "SELECT id, employee_id, status, resume_state FROM employee_tasks WHERE company_id=? ORDER BY created_at",
            (env["company_id"],),
        )
        assert len(emp) == 2
        first, second = emp
        assert first["employee_id"] == env["alice_id"]
        assert first["status"] == "assigned"
        assert first["resume_state"] is None
        assert second["employee_id"] == env["bob_id"]
        assert second["status"] == "waiting_resource"
        assert second["resume_state"] == "assigned"

        # Serial dependency edge alice -> bob.
        edges = await _rows(
            db,
            "SELECT employee_task_id, depends_on_task_id FROM employee_task_dependencies WHERE company_id=?",
            (env["company_id"],),
        )
        assert len(edges) == 1
        assert edges[0]["employee_task_id"] == second["id"]
        assert edges[0]["depends_on_task_id"] == first["id"]

        # Only the first segment got a run.
        runs = await _rows(db, "SELECT employee_task_id FROM agent_runs WHERE company_id=?", (env["company_id"],))
        assert [row["employee_task_id"] for row in runs] == [first["id"]]

        # The second segment froze a dispatch spec for lazy dispatch.
        specs = await _rows(
            db,
            "SELECT employee_task_id, profile_version_id, model_id, workspace_grant_id, department_revision_id,"
            " required_capability_tags_json"
            " FROM employee_task_dispatch_specs WHERE company_id=? AND company_task_id=?",
            (env["company_id"], env["task_id"]),
        )
        assert [row["employee_task_id"] for row in specs] == [second["id"]]
        assert specs[0]["profile_version_id"]
        assert specs[0]["workspace_grant_id"]
        assert json.loads(specs[0]["required_capability_tags_json"]) == ["code", "review"]
        run_spec = await _rows(
            db,
            "SELECT run_spec_json FROM agent_runs WHERE employee_task_id=?",
            (first["id"],),
        )
        assert json.loads(run_spec[0]["run_spec_json"])["required_capability_tags"] == ["code", "review"]


class TestDuplicateDeliverableRejection:
    @pytest.mark.asyncio
    async def test_duplicate_artifact_type_rejected_at_confirm(self, db: Any, strategy_env: dict[str, str]) -> None:
        """S2-2: two deliverables sharing an artifact_type would collide on the
        deliverable_review_specs UNIQUE key and silently drop the second spec
        (no reviews, or the wrong ones).  Reject the plan loudly at confirm
        instead of letting it degrade quietly."""
        env = strategy_env
        sha = await _register_plan(
            db,
            env,
            [
                _deliverable("independent_drafts", [env["alice_id"]], [env["carol_id"]], artifact_type="code"),
                _deliverable("independent_drafts", [env["bob_id"]], [env["carol_id"]], artifact_type="code"),
            ],
        )
        with pytest.raises(ValueError, match="DUPLICATE_DELIVERABLE_ARTIFACT_TYPE"):
            await _confirm(db, env, sha)

        # Confirm aborted before any write: no employee tasks, no specs.
        emp = await _rows(db, "SELECT 1 FROM employee_tasks WHERE company_id=?", (env["company_id"],))
        assert emp == []
        specs = await _rows(
            db,
            "SELECT 1 FROM deliverable_review_specs WHERE company_id=? AND company_task_id=?",
            (env["company_id"], env["task_id"]),
        )
        assert specs == []
