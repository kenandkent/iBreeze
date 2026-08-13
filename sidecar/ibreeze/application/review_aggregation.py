"""Review verdict fusion + reviewer stats flywheel, wired into the submit txn.

:class:`ReviewAggregationService.on_report_submitted` runs *inside* the
``SubmitReview`` command transaction (single writer), so the fused verdict,
the idempotent per-report scores and any automatic round+1 assignment are all
atomic with the report write.  Replays are idempotent: ``report_id`` PK guards
the score ledger, ``credited`` guards the stats update, and the rerun insert is
guarded by ``UNIQUE(artifact_id, reviewer_employee_id, review_round)``.

Safety boundary is untouched: the completion gates (``_review_not_passed`` /
``_blocking_issue_open``) keep their all-pass + one-veto semantics.  Fusion only
decides *whether to rerun*, never overrides a hard veto.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from ibreeze.domain.review.aggregation import (
    FusedVerdict,
    ReportScore,
    compute_weight,
    fuse_verdicts,
    rerun_decision,
)
from ibreeze.domain.review.repository import ReviewRepository
from ibreeze.persistence.types import DomainEventRecord, OutboxRecord

_SEVERITY_RANK = {"blocker": 4, "high": 3, "medium": 2, "low": 1}
_SEVERITY_LABEL = {4: "blocker", 3: "high", 2: "medium", 1: "low"}
_DEFAULT_ROUNDS = 2
_DEFAULT_THRESHOLD = 0.7


@dataclass(frozen=True, slots=True)
class AggregationOutcome:
    """What the submit-txn aggregation produced, for the caller to persist.

    ``fused`` is the post-submit fusion; ``rerun_event`` / ``rerun_outbox``
    carry the auto round+1 ``review.assigned`` event when one was created, so
    the surrounding ``SubmitReview`` command can write them atomically with the
    report — the same audit trail the manual rerun path writes.
    """

    fused: FusedVerdict
    rerun_event: DomainEventRecord | None = None
    rerun_outbox: OutboxRecord | None = None


class ReviewAggregationService:
    """Fuse reviewer verdicts after each submit and drive auto-rerun."""

    def __init__(self, repo: ReviewRepository) -> None:
        self._repo = repo

    async def on_report_submitted(
        self,
        session: Any,
        *,
        company_id: Any,
        assignment: Any,
    ) -> AggregationOutcome:
        """Record, fuse and persist the post-submit aggregation state."""
        await self._record_score(session, company_id=company_id, assignment=assignment)

        scores = await self._load_scores(session, company_id=company_id, artifact_id=assignment.artifact_id)
        open_blockers = await self._open_blocker_high_count(session, company_id=company_id, artifact_id=assignment.artifact_id)
        fused = fuse_verdicts(scores, open_blocker_high_issues=open_blockers)

        rounds, threshold = await self._spec(session, company_id=company_id, artifact_id=assignment.artifact_id)
        current_round, pending = await self._round_state(session, company_id=company_id, artifact_id=assignment.artifact_id)
        decision = rerun_decision(
            fused,
            current_round=current_round,
            review_rounds=rounds,
            pending_current_round=pending,
            threshold=threshold,
        )

        await self._upsert_verdict(
            session,
            company_id=company_id,
            artifact_id=assignment.artifact_id,
            artifact_sha256=assignment.artifact_sha256,
            fused=fused,
            decision=decision,
            review_rounds=rounds,
        )

        if decision in ("pass", "exhausted"):
            await self._finalize_scores(session, company_id=company_id, artifact_id=assignment.artifact_id, fused=fused)
        rerun_event: DomainEventRecord | None = None
        rerun_outbox: OutboxRecord | None = None
        if decision == "rerun":
            rerun_event, rerun_outbox = await self._create_auto_rerun(session, company_id=company_id, artifact_id=assignment.artifact_id)
        return AggregationOutcome(
            fused=fused,
            rerun_event=rerun_event,
            rerun_outbox=rerun_outbox,
        )

    # -- score ledger ---------------------------------------------------------

    async def _record_score(self, session: Any, *, company_id: Any, assignment: Any) -> None:
        """Insert the just-submitted report's score row (idempotent via PK)."""
        cursor = await session.execute(
            """SELECT rr.id, rr.verdict, ra.reviewer_employee_id
               FROM review_reports rr
               JOIN review_assignments ra ON ra.id=rr.assignment_id
               WHERE rr.assignment_id=? AND rr.company_id=?
               ORDER BY rr.created_at DESC LIMIT 1""",
            (str(assignment.id), str(company_id)),
        )
        row = await cursor.fetchone()
        if row is None:
            return
        report_id = str(row["id"])
        exists = await (await session.execute("SELECT 1 FROM review_report_scores WHERE report_id=?", (report_id,))).fetchone()
        if exists is not None:
            return
        issue_cursor = await session.execute(
            """SELECT COUNT(*) AS n,
                      MAX(CASE severity WHEN 'blocker' THEN 4 WHEN 'high' THEN 3
                          WHEN 'medium' THEN 2 ELSE 1 END) AS sev
               FROM review_issues WHERE review_report_id=? AND company_id=?""",
            (report_id, str(company_id)),
        )
        issue_row = await issue_cursor.fetchone()
        issue_count = int(issue_row["n"]) if issue_row else 0
        severity = _SEVERITY_LABEL.get(int(issue_row["sev"]), "low") if issue_row and issue_row["sev"] else "low"
        stats = await self._reviewer_stats(session, company_id, row["reviewer_employee_id"])
        weight = compute_weight(stats)
        await session.execute(
            """INSERT OR IGNORE INTO review_report_scores
               (report_id, assignment_id, artifact_id, company_id,
                reviewer_employee_id, verdict, severity_max, issue_count,
                weight, scored_at)
               VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))""",
            (
                report_id,
                str(assignment.id),
                str(assignment.artifact_id),
                str(company_id),
                str(row["reviewer_employee_id"]),
                row["verdict"],
                severity,
                issue_count,
                weight,
            ),
        )

    # -- fusion inputs --------------------------------------------------------

    async def _reviewer_stats(self, session: Any, company_id: Any, reviewer_id: Any) -> dict[str, object] | None:
        row = await (
            await session.execute(
                "SELECT accuracy, sample_count FROM reviewer_stats WHERE company_id=? AND reviewer_employee_id=?",
                (str(company_id), str(reviewer_id)),
            )
        ).fetchone()
        return {"accuracy": row["accuracy"], "sample_count": row["sample_count"]} if row else None

    async def _load_scores(self, session: Any, *, company_id: Any, artifact_id: Any) -> list[ReportScore]:
        # One opinion per reviewer: the independence product that drives
        # confidence only holds across distinct reviewers.  A single reviewer
        # who re-reviews in a later round (auto-rerun reuses the source
        # reviewer) contributes exactly one score — the latest round — so a
        # lone reviewer can never inflate confidence by re-submitting.
        cursor = await session.execute(
            """SELECT report_id, verdict, accuracy, sample_count FROM (
                   SELECT rr.id AS report_id, rr.verdict,
                          COALESCE(rs.accuracy, 0.0) AS accuracy,
                          COALESCE(rs.sample_count, 0) AS sample_count,
                          ROW_NUMBER() OVER (
                              PARTITION BY ra.reviewer_employee_id
                              ORDER BY ra.review_round DESC, rr.created_at DESC
                          ) AS rn
                   FROM review_reports rr
                   JOIN review_assignments ra ON ra.id=rr.assignment_id
                   JOIN artifacts a ON a.id=ra.artifact_id
                   LEFT JOIN reviewer_stats rs
                     ON rs.company_id=rr.company_id AND rs.reviewer_employee_id=ra.reviewer_employee_id
                   WHERE rr.company_id=? AND ra.artifact_id=? AND a.is_current=1
                     AND ra.reviewed_sha256=a.object_sha256 AND ra.status='submitted'
               ) WHERE rn=1""",
            (str(company_id), str(artifact_id)),
        )
        rows = await cursor.fetchall()
        return [
            ReportScore(
                report_id=str(row["report_id"]),
                verdict=row["verdict"],
                weight=compute_weight({"accuracy": row["accuracy"], "sample_count": row["sample_count"]}),
            )
            for row in rows
        ]

    async def _open_blocker_high_count(self, session: Any, *, company_id: Any, artifact_id: Any) -> int:
        """Same scope as the completion gate's ``_blocking_issue_open``."""
        cursor = await session.execute(
            """SELECT COUNT(*) AS n
               FROM review_issues ri
               JOIN review_reports rr ON rr.id=ri.review_report_id
               JOIN review_assignments ra ON ra.id=rr.assignment_id
               JOIN artifacts a ON a.id=ra.artifact_id
               WHERE ri.company_id=? AND ra.artifact_id=? AND a.is_current=1
                 AND ra.reviewed_sha256=a.object_sha256 AND ra.status='submitted'
                 AND ri.severity IN ('blocker','high')
                 AND ri.status NOT IN ('closed','rejected')
                 AND ri.superseded_by_artifact_id IS NULL""",
            (str(company_id), str(artifact_id)),
        )
        row = await cursor.fetchone()
        return int(row["n"]) if row else 0

    # -- spec + round state ---------------------------------------------------

    async def _spec(self, session: Any, *, company_id: Any, artifact_id: Any) -> tuple[int, float]:
        artifact = await (
            await session.execute(
                "SELECT company_task_id, artifact_type FROM artifacts WHERE id=? AND company_id=?",
                (str(artifact_id), str(company_id)),
            )
        ).fetchone()
        if artifact is None:
            return _DEFAULT_ROUNDS, _DEFAULT_THRESHOLD
        spec = await (
            await session.execute(
                "SELECT review_rounds, confidence_threshold FROM deliverable_review_specs"
                " WHERE company_id=? AND company_task_id=? AND artifact_type=?",
                (str(company_id), artifact["company_task_id"], artifact["artifact_type"]),
            )
        ).fetchone()
        if spec is None:
            return _DEFAULT_ROUNDS, _DEFAULT_THRESHOLD
        return int(spec["review_rounds"]), float(spec["confidence_threshold"])

    async def _round_state(self, session: Any, *, company_id: Any, artifact_id: Any) -> tuple[int, int]:
        cursor = await session.execute(
            """SELECT review_round, status FROM review_assignments
               WHERE company_id=? AND artifact_id=?""",
            (str(company_id), str(artifact_id)),
        )
        rows = await cursor.fetchall()
        if not rows:
            return 1, 0
        current_round = max(int(row["review_round"]) for row in rows)
        pending = sum(1 for row in rows if int(row["review_round"]) == current_round and row["status"] in ("assigned", "in_review"))
        return current_round, pending

    # -- persistence ----------------------------------------------------------

    async def _upsert_verdict(
        self,
        session: Any,
        *,
        company_id: Any,
        artifact_id: Any,
        artifact_sha256: str,
        fused: FusedVerdict,
        decision: str,
        review_rounds: int,
    ) -> None:
        score_json = json.dumps(
            {
                "verdict": fused.verdict,
                "confidence": fused.confidence,
                "hard_veto": fused.hard_veto,
                "decision": decision,
                "review_rounds": review_rounds,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        await session.execute(
            """INSERT INTO review_verdicts
               (company_id, artifact_id, artifact_sha256, verdict, confidence,
                hard_veto_triggered, rerun_exhausted, score_json, updated_at)
               VALUES (?,?,?,?,?,?,?,?,datetime('now'))
               ON CONFLICT(company_id, artifact_id) DO UPDATE SET
                 artifact_sha256=excluded.artifact_sha256,
                 verdict=excluded.verdict,
                 confidence=excluded.confidence,
                 hard_veto_triggered=excluded.hard_veto_triggered,
                 rerun_exhausted=excluded.rerun_exhausted,
                 score_json=excluded.score_json,
                 updated_at=excluded.updated_at""",
            (
                str(company_id),
                str(artifact_id),
                artifact_sha256,
                fused.verdict,
                fused.confidence,
                1 if fused.hard_veto else 0,
                1 if decision == "exhausted" else 0,
                score_json,
            ),
        )

    async def _finalize_scores(
        self,
        session: Any,
        *,
        company_id: Any,
        artifact_id: Any,
        fused: FusedVerdict,
    ) -> None:
        """Score every uncredited report against the final fused verdict.

        Only reached when the fusion is final (``pass``/``exhausted``), so a
        partially-submitted round never writes provisional accuracy.
        """
        cursor = await session.execute(
            """SELECT report_id, reviewer_employee_id, verdict, issue_count
               FROM review_report_scores
               WHERE company_id=? AND artifact_id=? AND credited=0""",
            (str(company_id), str(artifact_id)),
        )
        rows = await cursor.fetchall()
        for row in rows:
            contribution = 1.0 if row["verdict"] == fused.verdict else 0.0
            await session.execute(
                """INSERT OR IGNORE INTO reviewer_stats
                   (company_id, reviewer_employee_id, reviews_completed,
                    reviews_with_issues, accuracy, sample_count, last_review_at)
                   VALUES (?,?,0,0,0,0,datetime('now'))""",
                (str(company_id), str(row["reviewer_employee_id"])),
            )
            await session.execute(
                """UPDATE reviewer_stats
                   SET accuracy=round(0.7*accuracy + 0.3*?, 3),
                       reviews_completed=reviews_completed+1,
                       reviews_with_issues=reviews_with_issues+?,
                       sample_count=sample_count+1,
                       last_review_at=datetime('now')
                   WHERE company_id=? AND reviewer_employee_id=?""",
                (contribution, 1 if int(row["issue_count"]) > 0 else 0, str(company_id), str(row["reviewer_employee_id"])),
            )
            await session.execute(
                "UPDATE review_report_scores SET credited=1, accuracy_contribution=? WHERE report_id=?",
                (contribution, str(row["report_id"])),
            )

    async def _create_auto_rerun(
        self, session: Any, *, company_id: Any, artifact_id: Any
    ) -> tuple[DomainEventRecord | None, OutboxRecord | None]:
        """Create a round+1 assignment for the artifact (respects round cap).

        Uses the most recent submitted report as the rerun source; reuses the
        repository's rerun validation (active reviewer, non-contributor,
        current artifact, hash match).  If the reviewer is no longer eligible,
        fall back to accepting the low-confidence verdict and record the
        exhaustion on the verdict row instead of failing the submit.

        Returns the ``review.assigned`` event/outbox rows for the surrounding
        submit command to persist atomically (``(None, None)`` when no rerun
        was created).
        """
        # Pick the source by highest round (deterministic): created_at alone is
        # ambiguous when two submitted reports share a timestamp (same-day
        # batches, fixed-clock tests) and would let an older round resubmit a
        # round+1 that already exists -> UNIQUE violation.
        cursor = await session.execute(
            """SELECT rr.id FROM review_reports rr
               JOIN review_assignments ra ON ra.id=rr.assignment_id
               WHERE rr.company_id=? AND ra.artifact_id=? AND ra.status='submitted'
               ORDER BY ra.review_round DESC, rr.created_at DESC LIMIT 1""",
            (str(company_id), str(artifact_id)),
        )
        row = await cursor.fetchone()
        if row is None:
            return None, None
        try:
            _assignment, event, outbox = await self._repo.create_rerun_assignment(
                session, company_id=UUID(str(company_id)), review_id=UUID(str(row["id"]))
            )
        except ValueError:
            await session.execute(
                "UPDATE review_verdicts SET rerun_exhausted=1 WHERE company_id=? AND artifact_id=?",
                (str(company_id), str(artifact_id)),
            )
            return None, None
        return event, outbox
