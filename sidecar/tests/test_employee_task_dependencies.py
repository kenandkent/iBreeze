"""Sequential refinement lazy dispatch: employee_task_dependencies + graph_advance.

``sequential_refinement`` chains contributors at confirm time with
``employee_task_dependencies``; every segment after the first is inserted
``waiting_resource`` with a frozen ``employee_task_dispatch_specs`` row and no
run.  :func:`advance_employee_task_graph` then dispatches a waiting segment
exactly once, and only once *all* of its upstream segments are ``accepted``.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from ibreeze.orchestration.confirm_plan import ConfirmPlanCommand, confirm_and_dispatch
from ibreeze.orchestration.dispatch_strategies import advance_employee_task_graph


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
async def chain_env(db: Any) -> dict[str, str]:
    """Company + dept + three active employees, one task, one workspace."""
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
        " current_revision_id, leader_employee_id, department_conversation_id,"
        " status, created_at, updated_at, version) VALUES (?,?,'standard','engineering',?,?,?,"
        " 'active',?,?,1)",
        (dept_id, company_id, dept_rev_id, _id(), dept_conv_id, now, now),
    )
    alice_id = await _insert_employee(db, company_id, dept_id, version_id, now, "Alice")
    bob_id = await _insert_employee(db, company_id, dept_id, version_id, now, "Bob")
    carol_id = await _insert_employee(db, company_id, dept_id, version_id, now, "Carol")
    await db.execute(
        "INSERT INTO conversations"
        " (id, company_id, conversation_type, status, created_at)"
        " VALUES (?,?,'company','active',?)",
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
    contributors: list[str],
) -> str:
    """Register a plan with one sequential_refinement deliverable."""
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
                    "deliverables": [
                        {
                            "title": "Deliverable",
                            "description": "Thing",
                            "artifact_type": "code",
                            "review_strategy": "sequential_refinement",
                            "review_rounds": 2,
                            "contributor_employee_ids": contributors,
                            "reviewer_employee_ids": [],
                        }
                    ],
                    "acceptance_criteria": ["Works"],
                    "dependency_refs": [],
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


async def _rows(db: Any, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    return await (await db.execute(sql, params)).fetchall()


async def _accept(db: Any, task_id: str, company_id: str, now: str) -> None:
    """Simulate the AcceptEmployeeTaskHandler state transition."""
    row = await (
        await db.execute(
            "SELECT version, status FROM employee_tasks WHERE id=? AND company_id=?",
            (task_id, company_id),
        )
    ).fetchone()
    await db.execute(
        "UPDATE employee_tasks SET status='accepted', resume_state=NULL, updated_at=?, version=version+1"
        " WHERE id=? AND company_id=? AND status=? AND version=?",
        (now, task_id, company_id, row["status"], row["version"]),
    )


class TestSequentialChain:
    @pytest.mark.asyncio
    async def test_confirm_chains_and_defers(self, db: Any, chain_env: dict[str, str]) -> None:
        env = chain_env
        sha = await _register_plan(db, env, [env["alice_id"], env["bob_id"], env["carol_id"]])
        result = await _confirm(db, env, sha)
        assert result["status"] == "confirmed"

        tasks = await _rows(
            db,
            "SELECT id, employee_id, status, resume_state FROM employee_tasks"
            " WHERE company_id=? ORDER BY created_at",
            (env["company_id"],),
        )
        assert [t["employee_id"] for t in tasks] == [env["alice_id"], env["bob_id"], env["carol_id"]]
        assert tasks[0]["status"] == "assigned"
        assert tasks[0]["resume_state"] is None
        assert tasks[1]["status"] == "waiting_resource"
        assert tasks[1]["resume_state"] == "assigned"
        assert tasks[2]["status"] == "waiting_resource"
        assert tasks[2]["resume_state"] == "assigned"

        # Chain edges alice->bob, bob->carol.
        edges = await _rows(
            db,
            "SELECT employee_task_id, depends_on_task_id FROM employee_task_dependencies"
            " WHERE company_id=?",
            (env["company_id"],),
        )
        assert {(e["employee_task_id"], e["depends_on_task_id"]) for e in edges} == {
            (tasks[1]["id"], tasks[0]["id"]),
            (tasks[2]["id"], tasks[1]["id"]),
        }

        # Deferred segments froze dispatch specs.
        specs = await _rows(
            db,
            "SELECT employee_task_id FROM employee_task_dispatch_specs WHERE company_id=? AND company_task_id=?",
            (env["company_id"], env["task_id"]),
        )
        assert {s["employee_task_id"] for s in specs} == {tasks[1]["id"], tasks[2]["id"]}

        # Only the first segment has a run.
        runs = await _rows(db, "SELECT employee_task_id FROM agent_runs WHERE company_id=?", (env["company_id"],))
        assert [r["employee_task_id"] for r in runs] == [tasks[0]["id"]]

    @pytest.mark.asyncio
    async def test_advance_dispenses_one_hop_at_a_time(self, db: Any, chain_env: dict[str, str]) -> None:
        env = chain_env
        sha = await _register_plan(db, env, [env["alice_id"], env["bob_id"], env["carol_id"]])
        assert (await _confirm(db, env, sha))["status"] == "confirmed"
        tasks = await _rows(
            db,
            "SELECT id, employee_id FROM employee_tasks WHERE company_id=? ORDER BY created_at",
            (env["company_id"],),
        )
        alice, bob, carol = tasks

        # Accepting alice advances bob (single upstream) but not carol, whose
        # upstream bob is not yet accepted.
        await _accept(db, alice["id"], env["company_id"], _now())
        result = await advance_employee_task_graph(
            db,
            company_id=env["company_id"],
            accepted_task_id=alice["id"],
        )
        assert result["status"] == "advanced"
        assert result["dispatched"] == [bob["id"]]

        bob_row = await (await db.execute(
            "SELECT status, resume_state FROM employee_tasks WHERE id=?", (bob["id"],)
        )).fetchone()
        assert bob_row["status"] == "assigned"
        assert bob_row["resume_state"] is None
        carol_row = await (await db.execute(
            "SELECT status FROM employee_tasks WHERE id=?", (carol["id"],)
        )).fetchone()
        assert carol_row["status"] == "waiting_resource"

        runs = await _rows(db, "SELECT employee_task_id FROM agent_runs WHERE company_id=?", (env["company_id"],))
        assert {r["employee_task_id"] for r in runs} == {alice["id"], bob["id"]}

        # Replaying the same advance is a no-op (bob no longer waiting_resource).
        replay = await advance_employee_task_graph(
            db,
            company_id=env["company_id"],
            accepted_task_id=alice["id"],
        )
        assert replay["dispatched"] == []

        # Now accepting bob unblocks carol.
        await _accept(db, bob["id"], env["company_id"], _now())
        result = await advance_employee_task_graph(
            db,
            company_id=env["company_id"],
            accepted_task_id=bob["id"],
        )
        assert result["dispatched"] == [carol["id"]]
        runs = await _rows(db, "SELECT employee_task_id FROM agent_runs WHERE company_id=?", (env["company_id"],))
        assert {r["employee_task_id"] for r in runs} == {alice["id"], bob["id"], carol["id"]}

    @pytest.mark.asyncio
    async def test_multi_upstream_waits_for_all(self, db: Any, chain_env: dict[str, str]) -> None:
        env = chain_env
        sha = await _register_plan(db, env, [env["alice_id"], env["bob_id"], env["carol_id"]])
        assert (await _confirm(db, env, sha))["status"] == "confirmed"
        tasks = await _rows(
            db,
            "SELECT id, employee_id FROM employee_tasks WHERE company_id=? ORDER BY created_at",
            (env["company_id"],),
        )
        alice, bob, carol = tasks

        # Give carol a second upstream edge to alice: carol now depends on
        # both bob and alice, so alice's accept alone must not dispatch it.
        await db.execute(
            "INSERT INTO employee_task_dependencies (employee_task_id, depends_on_task_id, company_id, created_at)"
            " VALUES (?,?,?,?)",
            (carol["id"], alice["id"], env["company_id"], env["now"]),
        )

        await _accept(db, alice["id"], env["company_id"], _now())
        result = await advance_employee_task_graph(
            db,
            company_id=env["company_id"],
            accepted_task_id=alice["id"],
        )
        # Only bob has all upstreams satisfied.
        assert result["dispatched"] == [bob["id"]]
        carol_row = await (await db.execute(
            "SELECT status FROM employee_tasks WHERE id=?", (carol["id"],)
        )).fetchone()
        assert carol_row["status"] == "waiting_resource"

    @pytest.mark.asyncio
    async def test_lazy_dispatch_fails_when_binding_not_live(
        self, db: Any, chain_env: dict[str, str]
    ) -> None:
        """S2-1: a dependent whose frozen binding went stale is transitioned to
        'failed' instead of being left stuck in waiting_resource or silently
        skipped (which would strand the segment forever)."""
        env = chain_env
        sha = await _register_plan(db, env, [env["alice_id"], env["bob_id"], env["carol_id"]])
        assert (await _confirm(db, env, sha))["status"] == "confirmed"
        tasks = await _rows(
            db,
            "SELECT id, employee_id FROM employee_tasks WHERE company_id=? ORDER BY created_at",
            (env["company_id"],),
        )
        alice, bob, carol = tasks

        # Bob's employee is deactivated before his segment would dispatch.
        await db.execute("UPDATE employees SET status='inactive' WHERE id=?", (env["bob_id"],))

        await _accept(db, alice["id"], env["company_id"], _now())
        result = await advance_employee_task_graph(
            db,
            company_id=env["company_id"],
            accepted_task_id=alice["id"],
        )
        assert result["dispatched"] == []
        assert result["failed"] == [bob["id"]]
        bob_row = await (await db.execute(
            "SELECT status, resume_state FROM employee_tasks WHERE id=?", (bob["id"],)
        )).fetchone()
        assert bob_row["status"] == "failed"
        assert bob_row["resume_state"] is None
        # No run was built for a failed segment.
        runs = await _rows(db, "SELECT employee_task_id FROM agent_runs WHERE company_id=?", (env["company_id"],))
        assert {r["employee_task_id"] for r in runs} == {alice["id"]}
        # Carol still waits on bob (never accepted).
        carol_row = await (await db.execute(
            "SELECT status FROM employee_tasks WHERE id=?", (carol["id"],)
        )).fetchone()
        assert carol_row["status"] == "waiting_resource"
