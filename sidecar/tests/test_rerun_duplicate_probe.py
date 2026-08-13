"""Adversarial probe: can the auto-rerun path in review_aggregation.py raise an
uncaught sqlite3.IntegrityError from create_rerun_assignment's plain INSERT?

The claim: when (artifact, reviewer, round+1) already exists, the INSERT throws
IntegrityError which is not caught by `except ValueError` at
review_aggregation.py:355 and rolls back the whole SubmitReview txn.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from ibreeze.application.review_aggregation import ReviewAggregationService
from ibreeze.domain.review.entities import ReviewAssignment
from ibreeze.domain.review.repository import ReviewRepository


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


async def _setup(db: Any) -> dict[str, str]:
    now = _now()
    company_id = _id()
    task_id = _id()
    dept_task_id = _id()
    alice_id = _id()
    bob_id = _id()
    carol_id = _id()

    await db.execute("PRAGMA foreign_keys = OFF")

    async def _employee(employee_id: str, name: str) -> None:
        await db.execute(
            "INSERT INTO employees"
            " (id, company_id, department_id, display_name, normalized_display_name,"
            "  base_profile_version_id, workflow_role, status, created_at, updated_at, version)"
            " VALUES (?,?,?,?,?,?,'member','active',?,?,1)",
            (employee_id, company_id, _id(), name, name.lower(), _id(), now, now),
        )

    await _employee(alice_id, "Alice")
    await _employee(bob_id, "Bob")
    await _employee(carol_id, "Carol")

    # review_rounds = 3 so that a fresh round-1 submit resolves to "rerun".
    await db.execute(
        "INSERT INTO deliverable_review_specs"
        " (id, company_id, company_task_id, department_task_id, artifact_type,"
        "  review_strategy, contributor_employee_ids_json, reviewer_employee_ids_json,"
        "  review_rounds, confidence_threshold, created_at)"
        " VALUES (?,?,?,?,'document','independent_drafts',?,?,3,0.7,?)",
        (
            _id(),
            company_id,
            task_id,
            dept_task_id,
            json.dumps([alice_id]),
            json.dumps([bob_id, carol_id]),
            now,
        ),
    )
    await db.execute("PRAGMA foreign_keys = ON")

    return {
        "company_id": company_id,
        "task_id": task_id,
        "dept_task_id": dept_task_id,
        "alice_id": alice_id,
        "bob_id": bob_id,
        "carol_id": carol_id,
        "now": now,
    }


async def _publish_artifact(db: Any, env: dict[str, str], sha: str) -> str:
    artifact_id = _id()
    await db.execute(
        "INSERT INTO artifacts"
        " (id, company_id, company_task_id, artifact_type, logical_name, object_sha256,"
        "  object_size, media_type, metadata_json, is_current, created_by_type, created_at)"
        " VALUES (?,?,?,'document','x.py',?,10,'text/x-python','{}',1,'user',?)",
        (artifact_id, env["company_id"], env["task_id"], sha, env["now"]),
    )
    await db.execute(
        "INSERT INTO artifact_contributors (artifact_id, company_id, employee_id) VALUES (?,?,?)",
        (artifact_id, env["company_id"], env["alice_id"]),
    )
    return artifact_id


async def _assignment(
    db: Any,
    env: dict[str, str],
    artifact_id: str,
    sha: str,
    reviewer_id: str,
    round_no: int,
    status: str = "assigned",
) -> ReviewAssignment:
    assignment_id = _id()
    await db.execute(
        "INSERT INTO review_assignments"
        " (id, company_id, artifact_id, reviewer_employee_id, review_round,"
        "  reviewed_sha256, status, assigned_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (assignment_id, env["company_id"], artifact_id, reviewer_id, round_no, sha, status, env["now"]),
    )
    return ReviewAssignment(
        id=UUID(assignment_id),
        company_id=UUID(env["company_id"]),
        artifact_id=UUID(artifact_id),
        artifact_sha256=sha,
        reviewer_employee_id=UUID(reviewer_id),
        state=status,
        version=1,
    )


async def _report(db: Any, env: dict[str, str], assignment_id: str, artifact_id: str, sha: str) -> str:
    report_id = _id()
    await db.execute(
        "INSERT INTO review_reports"
        " (id, company_id, assignment_id, reviewer_run_id, reviewed_artifact_id,"
        "  reviewed_sha256, verdict, report_artifact_id, created_at, version)"
        " VALUES (?,?,?,?,?,?,?,?,?,1)",
        (
            report_id,
            env["company_id"],
            assignment_id,
            _id(),
            artifact_id,
            sha,
            "pass",
            artifact_id,
            env["now"],
        ),
    )
    return report_id


class TestClaimedState:
    @pytest.mark.asyncio
    async def test_normal_two_reviewer_round_progression_no_conflict(self, db: Any) -> None:
        """Drive the real decision loop through all rounds with a single reviewer;
        assert no IntegrityError escapes and no duplicate (artifact, reviewer, round)
        rows ever get created."""
        env = await _setup(db)
        sha = _sha256("v1")
        artifact_id = await _publish_artifact(db, env, sha)
        service = ReviewAggregationService(ReviewRepository())

        # Bob submits round 1 -> low confidence (single score, weight 0.5).
        bob_a = await _assignment(db, env, artifact_id, sha, env["bob_id"], 1)
        await _report(db, env, str(bob_a.id), artifact_id, sha)
        await db.execute(
            "UPDATE review_assignments SET status='submitted' WHERE id=?",
            (str(bob_a.id),),
        )
        await service.on_report_submitted(db, company_id=env["company_id"], assignment=bob_a)
        # Bob round-2 must be auto-created.
        assigns = await (
            await db.execute(
                "SELECT reviewer_employee_id, review_round, status FROM review_assignments WHERE artifact_id=? ORDER BY review_round",
                (artifact_id,),
            )
        ).fetchall()
        rounds = [(r["reviewer_employee_id"], r["review_round"], r["status"]) for r in assigns]
        assert (env["bob_id"], 2, "assigned") in rounds

        # Bob submits the AUTO-CREATED round 2 -> low confidence -> auto round 3.
        r2 = await (
            await db.execute(
                "SELECT id FROM review_assignments WHERE artifact_id=? AND review_round=2",
                (artifact_id,),
            )
        ).fetchone()
        bob2 = ReviewAssignment(
            id=UUID(r2["id"]),
            company_id=UUID(env["company_id"]),
            artifact_id=UUID(artifact_id),
            artifact_sha256=sha,
            reviewer_employee_id=UUID(env["bob_id"]),
            state="assigned",
            version=1,
        )
        await _report(db, env, str(bob2.id), artifact_id, sha)
        await db.execute("UPDATE review_assignments SET status='submitted' WHERE id=?", (str(bob2.id),))
        await service.on_report_submitted(db, company_id=env["company_id"], assignment=bob2)

        # Dedup: a reviewer contributes exactly ONE opinion (the latest round),
        # so bob's two passes still fuse to confidence 0.5 (< 0.7 threshold) ->
        # rerun again -> auto round 3.  No fake 0.75 pass, no IntegrityError.
        assigns = await (
            await db.execute(
                "SELECT reviewer_employee_id, review_round, status FROM review_assignments WHERE artifact_id=? ORDER BY review_round",
                (artifact_id,),
            )
        ).fetchall()
        keys = [(r["reviewer_employee_id"], r["review_round"], r["status"]) for r in assigns]
        assert keys == [
            (env["bob_id"], 1, "submitted"),
            (env["bob_id"], 2, "submitted"),
            (env["bob_id"], 3, "assigned"),
        ], keys
        assert len(keys) == len({(k[0], k[1]) for k in keys}), f"duplicate (reviewer, round): {keys}"

    @pytest.mark.asyncio
    async def test_replay_of_submit_never_duplicates(self, db: Any) -> None:
        """Re-invoking on_report_submitted for the SAME round-1 assignment (the
        closest reachable analogue of 're-submit') must not create round+1 twice."""
        env = await _setup(db)
        sha = _sha256("v1")
        artifact_id = await _publish_artifact(db, env, sha)
        bob_a = await _assignment(db, env, artifact_id, sha, env["bob_id"], 1)
        service = ReviewAggregationService(ReviewRepository())

        await _report(db, env, str(bob_a.id), artifact_id, sha)
        await db.execute("UPDATE review_assignments SET status='submitted' WHERE id=?", (str(bob_a.id),))
        await service.on_report_submitted(db, company_id=env["company_id"], assignment=bob_a)

        # Replay the same submit: pending round-2 forces wait_quorum, no 2nd insert.
        await service.on_report_submitted(db, company_id=env["company_id"], assignment=bob_a)

        assigns = await (
            await db.execute(
                "SELECT reviewer_employee_id, review_round FROM review_assignments WHERE artifact_id=? ORDER BY review_round",
                (artifact_id,),
            )
        ).fetchall()
        keys = [(r["reviewer_employee_id"], r["review_round"]) for r in assigns]
        assert len(keys) == len(set(keys)), f"duplicate (reviewer, round): {keys}"
        assert (env["bob_id"], 2) in keys
        assert (env["bob_id"], 3) not in keys

    @pytest.mark.asyncio
    async def test_manual_rerun_after_auto_rerun_hits_integrity_error(self, db: Any) -> None:
        """Demonstrate where an IntegrityError IS reachable: a manual RerunReview
        on a report whose round+1 already exists (auto already created it)."""
        import sqlite3

        env = await _setup(db)
        sha = _sha256("v1")
        artifact_id = await _publish_artifact(db, env, sha)
        bob_a = await _assignment(db, env, artifact_id, sha, env["bob_id"], 1)
        service = ReviewAggregationService(ReviewRepository())

        await _report(db, env, str(bob_a.id), artifact_id, sha)
        await db.execute("UPDATE review_assignments SET status='submitted' WHERE id=?", (str(bob_a.id),))
        await service.on_report_submitted(db, company_id=env["company_id"], assignment=bob_a)

        report = await (
            await db.execute(
                "SELECT rr.id FROM review_reports rr JOIN review_assignments ra ON ra.id=rr.assignment_id WHERE ra.id=?",
                (str(bob_a.id),),
            )
        ).fetchone()
        assert report is not None
        try:
            await ReviewRepository().create_rerun_assignment(db, company_id=UUID(env["company_id"]), review_id=UUID(report["id"]))
            raise AssertionError("expected IntegrityError for manual rerun on existing round+1")
        except sqlite3.IntegrityError:
            pass  # This is the reachable collision -- but it lives in RerunReview, not SubmitReview.
