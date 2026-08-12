"""Deterministic multi-reviewer verdict fusion.

Pure functions (no DB, no IO) mapping OpenSquilla's probability-fusion idea
onto ibreeze's reviewer verdicts while keeping the hard safety boundary:

* hard veto  — any ``needs_changes``/``failed`` verdict or any open
  blocker/high issue immediately forces ``needs_changes`` with confidence 1.0;
* soft fusion — in the all-``pass`` case, each reviewer is weighted by their
  historical accuracy and the fused confidence is ``1 - prod(1 - w_i)``
  (independent-omission product).  A low-confidence pass may trigger an
  automatic round+1 rerun instead of silently accepting the deliverable.

Weights come from deterministic rules + historical stats (reviewer_stats),
never from ML: cold start returns the default weight, otherwise accuracy is
clamped to ``[0.30, 0.95]`` so a single good/bad streak cannot dominate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_MIN_ACCURACY = 0.30
_MAX_ACCURACY = 0.95
_DEFAULT_WEIGHT = 0.5


@dataclass(frozen=True, slots=True)
class ReportScore:
    """One submitted report plus the reviewer's fused weight."""

    report_id: str
    verdict: str  # pass | needs_changes | failed
    weight: float  # reviewer historical accuracy (cold-start default 0.5)


@dataclass(frozen=True, slots=True)
class FusedVerdict:
    """Fused outcome for the current artifact."""

    verdict: str  # pass | needs_changes | failed
    confidence: float  # 0.0 .. 1.0
    hard_veto: bool


def compute_weight(
    stats: dict[str, Any] | None,
    *,
    min_sample: int = 5,
    default_weight: float = _DEFAULT_WEIGHT,
) -> float:
    """Map reviewer_stats to a fused weight.

    Cold start (``sample_count < min_sample``) keeps the neutral default so a
    reviewer is not trusted (or distrusted) until enough data accrues.
    Otherwise accuracy is clamped to ``[0.30, 0.95]`` and rounded to 3 places.
    """
    if stats is None or int(stats.get("sample_count", 0)) < min_sample:
        return default_weight
    accuracy = max(_MIN_ACCURACY, min(_MAX_ACCURACY, float(stats.get("accuracy", 0.0))))
    return round(accuracy, 3)


def fuse_verdicts(scores: list[ReportScore], *, open_blocker_high_issues: int) -> FusedVerdict:
    """Combine reviewer scores into a single fused verdict.

    Any non-pass verdict or open blocker/high issue is a hard veto
    (``needs_changes``, confidence 1.0).  All-pass fusion treats each pass as
    an independent observation: ``p_fail = prod(1 - w_i)`` and confidence is
    ``1 - p_fail``.  An empty score set has zero confidence (nothing yet
    actually reviewed this round is treated as unsupported).
    """
    if open_blocker_high_issues > 0 or any(score.verdict != "pass" for score in scores):
        return FusedVerdict(verdict="needs_changes", confidence=1.0, hard_veto=True)
    p_fail = 1.0
    for score in scores:
        p_fail *= 1.0 - score.weight
    return FusedVerdict(verdict="pass", confidence=round(1.0 - p_fail, 3), hard_veto=False)


def confidence_ok(verdict: FusedVerdict, threshold: float) -> bool:
    """A hard veto always "passes" the gate (it is not a rerun candidate)."""
    return verdict.hard_veto or verdict.confidence >= threshold


def rerun_decision(
    verdict: FusedVerdict,
    *,
    current_round: int,
    review_rounds: int,
    pending_current_round: int,
    threshold: float,
) -> str:
    """Decide the next action after a submit.

    Returns one of:

    * ``blocked``        - hard veto; the gate SQL blocks, no rerun.
    * ``wait_quorum``    - reviewers from the current round are still pending.
    * ``pass``           - all-pass fusion cleared the confidence threshold.
    * ``exhausted``      - rounds exhausted and confidence still low: accept
      (the deliverable is gated by the hard SQL checks; soft uncertainty is
      recorded in ``review_verdicts.rerun_exhausted``).
    * ``rerun``          - low confidence with rounds left: create round+1.
    """
    if verdict.hard_veto:
        return "blocked"
    if pending_current_round > 0:
        return "wait_quorum"
    if confidence_ok(verdict, threshold):
        return "pass"
    if current_round >= review_rounds:
        return "exhausted"
    return "rerun"
