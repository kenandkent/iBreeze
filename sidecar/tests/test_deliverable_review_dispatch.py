"""Lazy round-1 review seeding when a current artifact is published.

Every review strategy defers reviewer work: reviewers never get an employee
task at confirm time.  :func:`maybe_dispatch_deliverable_reviews` seeds one
``assigned`` round-1 assignment per still-active, non-contributor reviewer the
moment the current artifact is published, guarded by
``UNIQUE(artifact_id, reviewer_employee_id, review_round)`` so replays are
no-ops.  ``_artifact_create`` wires this into the artifact UnitOfWork.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from ibreeze.application.public_rpc import _artifact_create
from ibreeze.orchestration.dispatch_strategies import maybe_dispatch_deliverable_reviews


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


@pytest.fixture
async def review_env(db: Any) -> dict[str, str]:
    """Company + dept + contributor (alice) + reviewer (bob) + frozen spec."""
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
    task_id = _id()
    dept_task_id = _id()

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

    async def _employee(name: str) -> str:
        employee_id = _id()
        await db.execute(
            "INSERT INTO employees"
            " (id, company_id, department_id, display_name,"
            " normalized_display_name, base_profile_version_id, workflow_role,"
            " status, created_at, updated_at, version)"
            " VALUES (?,?,?,?,?,?,'member','active',?,?,1)",
            (employee_id, company_id, dept_id, name, name.lower(), version_id, now, now),
        )
        return employee_id

    alice_id = await _employee("Alice")
    bob_id = await _employee("Bob")
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
    await db.execute(
        "INSERT INTO company_tasks"
        " (id, company_id, title, company_conversation_id,"
        " user_message_event_id, status, created_at, updated_at, version)"
        " VALUES (?,?,?,?,?,'executing',?,?,1)",
        (task_id, company_id, "Build feature", conv_id, _id(), now, now),
    )
    await db.execute(
        "INSERT INTO department_tasks"
        " (id, company_id, company_task_id, department_id, stage_key,"
        " objective, deliverables_json, acceptance_criteria_json,"
        " status, created_at, updated_at, version)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,1)",
        (
            dept_task_id,
            company_id,
            task_id,
            dept_id,
            "fe-1",
            "Build feature",
            "[]",
            '["Works"]',
            "ready",
            now,
            now,
        ),
    )
    await db.execute(
        "INSERT INTO deliverable_review_specs"
        " (id, company_id, company_task_id, department_task_id, artifact_type,"
        " review_strategy, contributor_employee_ids_json,"
        " reviewer_employee_ids_json, review_rounds, confidence_threshold, created_at)"
        " VALUES (?,?,?,?,'document','independent_drafts',?,?,2,0.7,?)",
        (
            _id(),
            company_id,
            task_id,
            dept_task_id,
            json.dumps([alice_id]),
            json.dumps([bob_id, alice_id]),
            now,
        ),
    )

    await db.execute("PRAGMA foreign_keys = ON")

    return {
        "company_id": company_id,
        "dept_id": dept_id,
        "task_id": task_id,
        "dept_task_id": dept_task_id,
        "alice_id": alice_id,
        "bob_id": bob_id,
        "now": now,
    }


async def _rows(db: Any, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    return await (await db.execute(sql, params)).fetchall()


async def _assignments(db: Any, env: dict[str, str]) -> list[Any]:
    return await _rows(
        db,
        "SELECT reviewer_employee_id, review_round, status FROM review_assignments WHERE company_id=? ORDER BY reviewer_employee_id",
        (env["company_id"],),
    )


class TestMaybeDispatch:
    @pytest.mark.asyncio
    async def test_creates_round1_for_active_non_contributor_reviewer(self, db: Any, review_env: dict[str, str]) -> None:
        env = review_env
        artifact_id = _id()
        await db.execute(
            "INSERT INTO artifacts"
            " (id, company_id, company_task_id, artifact_type, logical_name,"
            " object_sha256, object_size, media_type, metadata_json, is_current,"
            " created_by_type, created_at)"
            " VALUES (?,?,?,'document','x.py',?,10,'text/x-python','{}',1,'user',?)",
            (artifact_id, env["company_id"], env["task_id"], _sha256("v1"), env["now"]),
        )
        await db.execute(
            "INSERT INTO artifact_contributors (artifact_id, company_id, employee_id) VALUES (?,?,?)",
            (artifact_id, env["company_id"], env["alice_id"]),
        )

        created = await maybe_dispatch_deliverable_reviews(
            db,
            company_id=env["company_id"],
            company_task_id=env["task_id"],
            artifact_id=artifact_id,
            artifact_type="document",
            is_current=True,
        )
        # Bob (reviewer, active, non-contributor) gets a round-1 assignment;
        # alice is a contributor so she is skipped even though listed.
        assert [c["reviewer_employee_id"] for c in created] == [env["bob_id"]]
        assigns = await _assignments(db, env)
        assert [(a["reviewer_employee_id"], a["review_round"], a["status"]) for a in assigns] == [(env["bob_id"], 1, "assigned")]
        # review.assigned is projection-only: outbox row present, no outbound topic mapping.
        outbox = await _rows(db, "SELECT topic FROM outbox_events")
        assert {o["topic"] for o in outbox} == {"review.assigned"}

    @pytest.mark.asyncio
    async def test_replay_is_idempotent(self, db: Any, review_env: dict[str, str]) -> None:
        env = review_env
        artifact_id = _id()
        await db.execute(
            "INSERT INTO artifacts"
            " (id, company_id, company_task_id, artifact_type, logical_name,"
            " object_sha256, object_size, media_type, metadata_json, is_current,"
            " created_by_type, created_at)"
            " VALUES (?,?,?,'document','x.py',?,10,'text/x-python','{}',1,'user',?)",
            (artifact_id, env["company_id"], env["task_id"], _sha256("v1"), env["now"]),
        )
        await db.execute(
            "INSERT INTO artifact_contributors (artifact_id, company_id, employee_id) VALUES (?,?,?)",
            (artifact_id, env["company_id"], env["alice_id"]),
        )

        first = await maybe_dispatch_deliverable_reviews(
            db,
            company_id=env["company_id"],
            company_task_id=env["task_id"],
            artifact_id=artifact_id,
            artifact_type="document",
            is_current=True,
        )
        assert len(first) == 1
        # Re-dispatch (e.g. outbox replay) creates nothing new.
        second = await maybe_dispatch_deliverable_reviews(
            db,
            company_id=env["company_id"],
            company_task_id=env["task_id"],
            artifact_id=artifact_id,
            artifact_type="document",
            is_current=True,
        )
        assert second == []
        assert len(await _assignments(db, env)) == 1

    @pytest.mark.asyncio
    async def test_non_current_artifact_is_ignored(self, db: Any, review_env: dict[str, str]) -> None:
        env = review_env
        artifact_id = _id()
        await db.execute(
            "INSERT INTO artifacts"
            " (id, company_id, company_task_id, artifact_type, logical_name,"
            " object_sha256, object_size, media_type, metadata_json, is_current,"
            " created_by_type, created_at)"
            " VALUES (?,?,?,'document','x.py',?,10,'text/x-python','{}',0,'user',?)",
            (artifact_id, env["company_id"], env["task_id"], _sha256("v1"), env["now"]),
        )
        created = await maybe_dispatch_deliverable_reviews(
            db,
            company_id=env["company_id"],
            company_task_id=env["task_id"],
            artifact_id=artifact_id,
            artifact_type="document",
            is_current=False,
        )
        assert created == []
        assert await _assignments(db, env) == []

    @pytest.mark.asyncio
    async def test_no_spec_or_mismatched_type_is_ignored(self, db: Any, review_env: dict[str, str]) -> None:
        env = review_env
        artifact_id = _id()
        await db.execute(
            "INSERT INTO artifacts"
            " (id, company_id, company_task_id, artifact_type, logical_name,"
            " object_sha256, object_size, media_type, metadata_json, is_current,"
            " created_by_type, created_at)"
            " VALUES (?,?,?,'log','README.md',?,10,'text/markdown','{}',1,'user',?)",
            (artifact_id, env["company_id"], env["task_id"], _sha256("v1"), env["now"]),
        )
        # Spec exists only for artifact_type 'document', not 'log'.
        created = await maybe_dispatch_deliverable_reviews(
            db,
            company_id=env["company_id"],
            company_task_id=env["task_id"],
            artifact_id=artifact_id,
            artifact_type="log",
            is_current=True,
        )
        assert created == []
        assert await _assignments(db, env) == []


class TestArtifactCreateWiring:
    @pytest.mark.asyncio
    async def test_artifact_create_seeds_review(self, db: Any, review_env: dict[str, str]) -> None:
        env = review_env
        result = await _artifact_create(
            db,
            {
                "company_id": env["company_id"],
                "company_task_id": env["task_id"],
                "artifact_type": "document",
                "content": "print('hello')",
                "filename": "hello.py",
                "mime_type": "text/x-python",
                "created_by_employee_id": env["alice_id"],
            },
        )
        assert result["artifact_id"]
        assigns = await _assignments(db, env)
        assert [(a["reviewer_employee_id"], a["review_round"]) for a in assigns] == [(env["bob_id"], 1)]

    @pytest.mark.asyncio
    async def test_deduplicated_publish_is_noop(self, db: Any, review_env: dict[str, str]) -> None:
        env = review_env
        content = "print('same')"
        first = await _artifact_create(
            db,
            {
                "company_id": env["company_id"],
                "company_task_id": env["task_id"],
                "artifact_type": "document",
                "content": content,
                "filename": "a.py",
                "mime_type": "text/x-python",
                "created_by_employee_id": env["alice_id"],
            },
        )
        assert len(await _assignments(db, env)) == 1
        # Same bytes -> CAS deduplicate -> no second dispatch.
        second = await _artifact_create(
            db,
            {
                "company_id": env["company_id"],
                "company_task_id": env["task_id"],
                "artifact_type": "document",
                "content": content,
                "filename": "b.py",
                "mime_type": "text/x-python",
                "created_by_employee_id": env["alice_id"],
            },
        )
        assert second["artifact_id"] == first["artifact_id"]
        assert len(await _assignments(db, env)) == 1
