"""Review verdict fusion + stats flywheel inside the submit transaction.

Drives :class:`ReviewAggregationService` against the real migration-backed DB:
single-row verdict upsert across two submits, idempotent score ledger, automatic
round+1 on low-confidence passes, ``rerun_exhausted`` when rounds run out, and
the hard-veto path never touching the score ledger.
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


@pytest.fixture
async def agg_env(db: Any) -> dict[str, str]:
    """Company with contributor alice + reviewers bob/carol and a review spec."""
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

    await db.execute(
        "INSERT INTO deliverable_review_specs"
        " (id, company_id, company_task_id, department_task_id, artifact_type,"
        "  review_strategy, contributor_employee_ids_json, reviewer_employee_ids_json,"
        "  review_rounds, confidence_threshold, created_at)"
        " VALUES (?,?,?,?,'document','independent_drafts',?,?,2,0.7,?)",
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
) -> ReviewAssignment:
    assignment_id = _id()
    await db.execute(
        "INSERT INTO review_assignments"
        " (id, company_id, artifact_id, reviewer_employee_id, review_round,"
        "  reviewed_sha256, status, assigned_at)"
        " VALUES (?,?,?,?,?,?,'assigned',?)",
        (assignment_id, env["company_id"], artifact_id, reviewer_id, round_no, sha, env["now"]),
    )
    return ReviewAssignment(
        id=UUID(assignment_id),
        company_id=UUID(env["company_id"]),
        artifact_id=UUID(artifact_id),
        artifact_sha256=sha,
        reviewer_employee_id=UUID(reviewer_id),
        state="assigned",
        version=1,
    )


async def _report(
    db: Any,
    env: dict[str, str],
    assignment: ReviewAssignment,
    sha: str,
    verdict: str,
    issues: tuple[tuple[str, str], ...] = (),
) -> None:
    report_id = _id()
    await db.execute(
        "INSERT INTO review_reports"
        " (id, company_id, assignment_id, reviewer_run_id, reviewed_artifact_id,"
        "  reviewed_sha256, verdict, report_artifact_id, created_at, version)"
        " VALUES (?,?,?,?,?,?,?,?,?,1)",
        (
            report_id,
            env["company_id"],
            str(assignment.id),
            _id(),
            str(assignment.artifact_id),
            sha,
            verdict,
            str(assignment.artifact_id),
            env["now"],
        ),
    )
    for severity, category in issues:
        await db.execute(
            "INSERT INTO review_issues"
            " (id, company_id, review_report_id, severity, category, description, expected,"
            "  actual, suggested_fix, evidence_refs_json, status, created_at, updated_at, version)"
            " VALUES (?,?,?,?,?,?,?,?,?,'[]','open',?,?,1)",
            (
                _id(),
                env["company_id"],
                report_id,
                severity,
                category,
                "desc",
                "expected",
                "actual",
                "suggested_fix",
                env["now"],
                env["now"],
            ),
        )


async def _submit(
    db: Any,
    env: dict[str, str],
    assignment: ReviewAssignment,
    sha: str,
    verdict: str,
    issues: tuple[tuple[str, str], ...] = (),
) -> None:
    """Simulate SubmitReviewHandler: create report + transition to submitted."""
    await _report(db, env, assignment, sha, verdict, issues)
    await db.execute(
        "UPDATE review_assignments SET status='submitted', submitted_at=?"
        " WHERE id=? AND status='assigned'",
        (env["now"], str(assignment.id)),
    )


async def _rows(db: Any, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    return await (await db.execute(sql, params)).fetchall()


def _service() -> ReviewAggregationService:
    return ReviewAggregationService(ReviewRepository())


class TestVerdictUpsert:
    @pytest.mark.asyncio
    async def test_two_submits_single_verdict_row_and_finalize(
        self, db: Any, agg_env: dict[str, str]
    ) -> None:
        env = agg_env
        sha = _sha256("v1")
        artifact_id = await _publish_artifact(db, env, sha)
        bob = await _assignment(db, env, artifact_id, sha, env["bob_id"], 1)
        carol = await _assignment(db, env, artifact_id, sha, env["carol_id"], 1)
        service = _service()

        # Bob submits first; carol still pending -> wait_quorum, no finalize.
        await _submit(db, env, bob, sha, "pass")
        await service.on_report_submitted(db, company_id=env["company_id"], assignment=bob)
        verdicts = await _rows(
            db,
            "SELECT verdict, confidence, hard_veto_triggered, rerun_exhausted, score_json"
            " FROM review_verdicts",
        )
        assert len(verdicts) == 1
        assert verdicts[0]["confidence"] == pytest.approx(0.5)
        assert json.loads(verdicts[0]["score_json"])["decision"] == "wait_quorum"
        assert await _rows(db, "SELECT 1 FROM reviewer_stats") == []

        # Carol submits: quorum reached, fused confidence 1 - 0.5*0.5 = 0.75.
        await _submit(db, env, carol, sha, "pass")
        await service.on_report_submitted(db, company_id=env["company_id"], assignment=carol)
        verdicts = await _rows(
            db,
            "SELECT verdict, confidence, hard_veto_triggered, rerun_exhausted, score_json"
            " FROM review_verdicts",
        )
        assert len(verdicts) == 1  # upserted, not a second row
        assert verdicts[0]["verdict"] == "pass"
        assert verdicts[0]["confidence"] == pytest.approx(0.75)
        assert verdicts[0]["hard_veto_triggered"] == 0
        assert json.loads(verdicts[0]["score_json"])["decision"] == "pass"

        # Finalized: both reports credited, each reviewer got exactly one sample.
        scores = await _rows(
            db,
            "SELECT report_id, credited, accuracy_contribution FROM review_report_scores"
            " ORDER BY report_id",
        )
        assert len(scores) == 2
        assert all(row["credited"] == 1 for row in scores)
        assert all(row["accuracy_contribution"] == 1.0 for row in scores)
        stats = await _rows(
            db, "SELECT sample_count, accuracy FROM reviewer_stats ORDER BY reviewer_employee_id"
        )
        assert [(row["sample_count"], row["accuracy"]) for row in stats] == [(1, 0.3), (1, 0.3)]

    @pytest.mark.asyncio
    async def test_replay_does_not_double_count(self, db: Any, agg_env: dict[str, str]) -> None:
        env = agg_env
        # Force rounds=1 so a replay of the final submit resolves to 'exhausted'
        # instead of creating a round+1 assignment.
        await db.execute("UPDATE deliverable_review_specs SET review_rounds=1")
        sha = _sha256("v1")
        artifact_id = await _publish_artifact(db, env, sha)
        bob = await _assignment(db, env, artifact_id, sha, env["bob_id"], 1)
        carol = await _assignment(db, env, artifact_id, sha, env["carol_id"], 1)
        service = _service()

        await _submit(db, env, bob, sha, "pass")
        await _submit(db, env, carol, sha, "pass")
        await service.on_report_submitted(db, company_id=env["company_id"], assignment=bob)
        await service.on_report_submitted(db, company_id=env["company_id"], assignment=carol)
        assert len(await _rows(db, "SELECT 1 FROM review_report_scores")) == 2
        sample_counts = [row["sample_count"] for row in await _rows(db, "SELECT sample_count FROM reviewer_stats")]
        assert sample_counts == [1, 1]

        # Replay the final submit: ledger must not double-count.
        await service.on_report_submitted(db, company_id=env["company_id"], assignment=carol)
        assert len(await _rows(db, "SELECT 1 FROM review_report_scores")) == 2
        sample_counts = [row["sample_count"] for row in await _rows(db, "SELECT sample_count FROM reviewer_stats")]
        assert sample_counts == [1, 1]
        assert len(await _rows(db, "SELECT 1 FROM review_verdicts")) == 1
        assert len(await _rows(db, "SELECT 1 FROM review_assignments")) == 2


class TestAutoRerun:
    @pytest.mark.asyncio
    async def test_low_confidence_pass_creates_round2(self, db: Any, agg_env: dict[str, str]) -> None:
        env = agg_env
        sha = _sha256("v1")
        artifact_id = await _publish_artifact(db, env, sha)
        bob = await _assignment(db, env, artifact_id, sha, env["bob_id"], 1)
        await _submit(db, env, bob, sha, "pass")

        outcome = await _service().on_report_submitted(
            db, company_id=env["company_id"], assignment=bob
        )

        assigns = await _rows(
            db,
            "SELECT reviewer_employee_id, review_round, status FROM review_assignments"
            " ORDER BY review_round",
        )
        assert [
            (row["reviewer_employee_id"], row["review_round"], row["status"]) for row in assigns
        ] == [
            (env["bob_id"], 1, "submitted"),
            (env["bob_id"], 2, "assigned"),
        ]
        verdict = (await _rows(db, "SELECT rerun_exhausted, score_json FROM review_verdicts"))[0]
        assert verdict["rerun_exhausted"] == 0
        assert json.loads(verdict["score_json"])["decision"] == "rerun"
        # Not finalized while the rerun is pending (provisional fusion).
        assert await _rows(db, "SELECT 1 FROM reviewer_stats") == []

        # F1: the auto round+1 assignment surfaces the same review.assigned
        # event/outbox the manual rerun path writes, for the submit handler to
        # persist atomically with the report (previously dropped inside the
        # service and never reachable by the outbox worker).
        assert outcome.rerun_event is not None
        assert outcome.rerun_outbox is not None
        assert outcome.rerun_outbox.topic == "review.assigned"
        payload = json.loads(outcome.rerun_event.payload_json)
        assert payload["reviewer_employee_id"] == env["bob_id"]
        r2 = await _rows(db, "SELECT id FROM review_assignments WHERE review_round=2")
        assert payload["assignment_id"] == r2[0]["id"]

    @pytest.mark.asyncio
    async def test_rounds_exhausted_marks_rerun_exhausted(self, db: Any, agg_env: dict[str, str]) -> None:
        env = agg_env
        await db.execute("UPDATE deliverable_review_specs SET review_rounds=1")
        sha = _sha256("v1")
        artifact_id = await _publish_artifact(db, env, sha)
        bob = await _assignment(db, env, artifact_id, sha, env["bob_id"], 1)
        await _submit(db, env, bob, sha, "pass")

        await _service().on_report_submitted(db, company_id=env["company_id"], assignment=bob)

        verdict = (await _rows(db, "SELECT rerun_exhausted, score_json FROM review_verdicts"))[0]
        assert verdict["rerun_exhausted"] == 1
        assert json.loads(verdict["score_json"])["decision"] == "exhausted"
        # No round+1 was created.
        assert len(await _rows(db, "SELECT 1 FROM review_assignments")) == 1
        # Finalized despite low confidence: one sample recorded.
        stats = await _rows(db, "SELECT sample_count, accuracy FROM reviewer_stats")
        assert [(row["sample_count"], row["accuracy"]) for row in stats] == [(1, 0.3)]

    @pytest.mark.asyncio
    async def test_same_reviewer_rerun_not_double_counted(
        self, db: Any, agg_env: dict[str, str]
    ) -> None:
        """A lone reviewer re-reviewing must not fuse their own opinions twice.

        Without per-reviewer dedup, bob's round-1 + round-2 passes would fuse
        to 1 - 0.5*0.5 = 0.75 and clear the threshold — treating one person's
        two opinions as two independent votes.  Dedup keeps one score per
        reviewer (latest round), so round 2 stays at confidence 0.5 and a
        round 3 is scheduled (review_rounds=3).
        """
        env = agg_env
        await db.execute("UPDATE deliverable_review_specs SET review_rounds=3")
        sha = _sha256("v1")
        artifact_id = await _publish_artifact(db, env, sha)
        bob1 = await _assignment(db, env, artifact_id, sha, env["bob_id"], 1)
        await _submit(db, env, bob1, sha, "pass")
        await _service().on_report_submitted(db, company_id=env["company_id"], assignment=bob1)

        # Round 2 already exists (the auto-rerun created it); reuse that row so
        # bob's second submit doesn't violate UNIQUE(artifact, reviewer, round).
        r2_row = (await _rows(db, "SELECT id FROM review_assignments WHERE review_round=2"))[0]
        bob2 = ReviewAssignment(
            id=UUID(r2_row["id"]),
            company_id=UUID(env["company_id"]),
            artifact_id=UUID(artifact_id),
            artifact_sha256=sha,
            reviewer_employee_id=UUID(env["bob_id"]),
            state="assigned",
            version=1,
        )
        await _submit(db, env, bob2, sha, "pass")
        await _service().on_report_submitted(db, company_id=env["company_id"], assignment=bob2)

        # Still low-confidence -> rerun again; round 3 created, no fake pass.
        assigns = await _rows(
            db,
            "SELECT review_round, status FROM review_assignments ORDER BY review_round",
        )
        assert [(row["review_round"], row["status"]) for row in assigns] == [
            (1, "submitted"),
            (2, "submitted"),
            (3, "assigned"),
        ]
        verdict = (await _rows(db, "SELECT score_json FROM review_verdicts"))[0]
        assert json.loads(verdict["score_json"])["decision"] == "rerun"


class TestHardVeto:
    @pytest.mark.asyncio
    async def test_needs_changes_blocks_and_skips_finalize(
        self, db: Any, agg_env: dict[str, str]
    ) -> None:
        env = agg_env
        sha = _sha256("v1")
        artifact_id = await _publish_artifact(db, env, sha)
        bob = await _assignment(db, env, artifact_id, sha, env["bob_id"], 1)
        await _submit(db, env, bob, sha, "needs_changes")

        outcome = await _service().on_report_submitted(
            db, company_id=env["company_id"], assignment=bob
        )
        assert outcome.fused.hard_veto
        assert outcome.fused.confidence == 1.0
        verdict = (await _rows(db, "SELECT verdict, hard_veto_triggered, score_json FROM review_verdicts"))[0]
        assert verdict["verdict"] == "needs_changes"
        assert verdict["hard_veto_triggered"] == 1
        assert json.loads(verdict["score_json"])["decision"] == "blocked"
        assert await _rows(db, "SELECT 1 FROM reviewer_stats") == []
        assert len(await _rows(db, "SELECT 1 FROM review_assignments")) == 1

    @pytest.mark.asyncio
    async def test_open_blocker_issue_is_hard_veto_even_with_pass_verdict(
        self, db: Any, agg_env: dict[str, str]
    ) -> None:
        env = agg_env
        sha = _sha256("v1")
        artifact_id = await _publish_artifact(db, env, sha)
        bob = await _assignment(db, env, artifact_id, sha, env["bob_id"], 1)
        # Artificial (the submit guard forbids pass-with-issues) but exercises the
        # open blocker/high count path independently of the verdict signal.
        await _submit(db, env, bob, sha, "pass", issues=(("blocker", "security"),))

        await _service().on_report_submitted(db, company_id=env["company_id"], assignment=bob)

        verdict = (await _rows(db, "SELECT hard_veto_triggered, score_json FROM review_verdicts"))[0]
        assert verdict["hard_veto_triggered"] == 1
        assert json.loads(verdict["score_json"])["decision"] == "blocked"
        assert await _rows(db, "SELECT 1 FROM reviewer_stats") == []
