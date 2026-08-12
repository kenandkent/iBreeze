"""Probe: does auto-rerun emit review.assigned event/outbox? Does gate block?"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from uuid import UUID

import pytest

from ibreeze.application.completion_handlers import EmployeeGate
from ibreeze.application.review_aggregation import ReviewAggregationService
from ibreeze.domain.review.entities import ReviewAssignment
from ibreeze.domain.review.repository import ReviewRepository


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


@pytest.fixture
async def env(db):
    now = _now()
    company_id = _id()
    task_id = _id()
    dept_task_id = _id()
    dept_id = _id()
    alice_id = _id()
    bob_id = _id()

    await db.execute("PRAGMA foreign_keys = OFF")

    await db.execute(
        "INSERT INTO company_tasks (id, company_id, company_conversation_id,"
        " user_message_event_id, title, status, created_at, updated_at, version)"
        " VALUES (?,?,?,?,?,?,?,?,1)",
        (task_id, company_id, "c", "e", "t", "executing", now, now),
    )
    await db.execute(
        "INSERT INTO departments (id, company_id, department_type, normalized_name,"
        " current_revision_id, leader_employee_id, department_conversation_id, status,"
        " created_at, updated_at, version) VALUES (?,?,?,?,?,?,?,?,?,?,1)",
        (dept_id, company_id, "standard", "dept", _id(), _id(), _id(), "active", now, now),
    )
    await db.execute(
        "INSERT INTO department_tasks (id, company_id, company_task_id, department_id,"
        " stage_key, objective, deliverables_json, acceptance_criteria_json, status,"
        " created_at, updated_at, version) VALUES (?,?,?,?,?,?,?,?,?,?,?,1)",
        (dept_task_id, company_id, task_id, dept_id, "dev", "o", "[]", "[]", "executing", now, now),
    )

    async def _employee(eid: str, name: str) -> None:
        await db.execute(
            "INSERT INTO employees (id, company_id, department_id, display_name,"
            " normalized_display_name, base_profile_version_id, workflow_role, status,"
            " created_at, updated_at, version)"
            " VALUES (?,?,?,?,?,?,'member','active',?,?,1)",
            (eid, company_id, dept_id, name, name.lower(), _id(), now, now),
        )

    await _employee(alice_id, "Alice")
    await _employee(bob_id, "Bob")

    et_id = _id()
    await db.execute(
        "INSERT INTO employee_tasks (id, company_id, department_task_id, employee_id,"
        " task_kind, objective, acceptance_criteria_json, status, resume_state,"
        " created_at, updated_at, version) VALUES (?,?,?,?,?,?,?,?,?,?,?,1)",
        (et_id, company_id, dept_task_id, alice_id, "standard", "o", "[]", "running", None, now, now),
    )

    await db.execute(
        "INSERT INTO deliverable_review_specs (id, company_id, company_task_id,"
        " department_task_id, artifact_type, review_strategy, contributor_employee_ids_json,"
        " reviewer_employee_ids_json, review_rounds, confidence_threshold, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,3,0.7,?)",
        (_id(), company_id, task_id, dept_task_id, "document", "independent_drafts",
         json.dumps([alice_id]), json.dumps([bob_id]), now),
    )

    sha = _sha256("v1")
    artifact_id = _id()
    await db.execute(
        "INSERT INTO artifacts (id, company_id, company_task_id, department_task_id,"
        " artifact_type, logical_name, object_sha256, object_size, media_type, metadata_json,"
        " is_current, created_by_type, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?)",
        (artifact_id, company_id, task_id, dept_task_id, "document", "x.py", sha, 10,
         "text/x-python", "{}", "user", now),
    )
    await db.execute(
        "INSERT INTO artifact_contributors (artifact_id, company_id, employee_id) VALUES (?,?,?)",
        (artifact_id, company_id, alice_id),
    )
    await db.execute("PRAGMA foreign_keys = ON")

    return {
        "company_id": company_id,
        "task_id": task_id,
        "dept_task_id": dept_task_id,
        "et_id": et_id,
        "alice_id": alice_id,
        "bob_id": bob_id,
        "artifact_id": artifact_id,
        "sha": sha,
        "now": now,
    }


async def _round1_submitted(db, env):
    """Bob already submitted round-1 pass; return the round-1 assignment object."""
    a1_id = _id()
    await db.execute(
        "INSERT INTO review_assignments (id, company_id, artifact_id, reviewer_employee_id,"
        " review_round, reviewed_sha256, status, assigned_at) VALUES (?,?,?,?,1,?,?,?)",
        (a1_id, env["company_id"], env["artifact_id"], env["bob_id"], env["sha"], "submitted", env["now"]),
    )
    await db.execute(
        "INSERT INTO review_reports (id, company_id, assignment_id, reviewer_run_id,"
        " reviewed_artifact_id, reviewed_sha256, verdict, report_artifact_id, created_at, version)"
        " VALUES (?,?,?,?,?,?,?,?,?,1)",
        (_id(), env["company_id"], a1_id, _id(), env["artifact_id"], env["sha"], "pass", env["artifact_id"], env["now"]),
    )
    return ReviewAssignment(
        id=UUID(a1_id), company_id=UUID(env["company_id"]), artifact_id=UUID(env["artifact_id"]),
        artifact_sha256=env["sha"], reviewer_employee_id=UUID(env["bob_id"]), state="submitted", version=1,
    )


@pytest.mark.asyncio
async def test_auto_rerun_emits_review_assigned_event_and_gate_blocks(db, env):
    """F1 regression: the auto round+1 assignment must persist a review.assigned
    event + outbox row (the same audit trail the manual rerun path writes) and
    surface them on the aggregation outcome, and the completion gate must still
    block while the round-2 assignment is pending."""
    a1 = await _round1_submitted(db, env)
    service = ReviewAggregationService(ReviewRepository())
    outcome = await service.on_report_submitted(db, company_id=env["company_id"], assignment=a1)
    await db.commit()

    # Round 2 auto-created and its event/outbox surfaced to the caller.
    assert outcome.rerun_event is not None
    assert outcome.rerun_outbox is not None
    assert outcome.rerun_outbox.topic == "review.assigned"
    r2 = await (await db.execute(
        "SELECT id FROM review_assignments WHERE artifact_id=? AND review_round=2",
        (env["artifact_id"],),
    )).fetchone()
    assert r2 is not None
    assert json.loads(outcome.rerun_event.payload_json)["assignment_id"] == r2["id"]

    # The outcome carries the full review.assigned payload (the submit handler
    # persists these rows atomically with the report).
    assert json.loads(outcome.rerun_event.payload_json)["assignment_id"] == r2["id"]
    assert json.loads(outcome.rerun_event.payload_json)["reviewer_employee_id"] == env["bob_id"]
    assert outcome.rerun_outbox.payload_json == outcome.rerun_event.payload_json
    assert outcome.rerun_outbox.domain_event_id == outcome.rerun_event.event_id

    # Gate still blocks: round-2 is assigned, so the artifact is not reviewed.
    gate = EmployeeGate()
    blockers = await gate.blockers(db, UUID(env["et_id"]), UUID(env["company_id"]))
    assert len(blockers) > 0

    # review runs only come from gateway.start (external): no agent_runs row yet.
    runs = await (await db.execute(
        "SELECT run_purpose, work_item_id, status FROM agent_runs WHERE company_id=?",
        (env["company_id"],),
    )).fetchall()
    assert len(runs) == 0
