"""Deterministic multi-reviewer verdict fusion (pure functions).

Covers the hard-veto / soft-fusion split, weight cold-start + clamping, the
confidence gate, and every branch of :func:`rerun_decision`.
"""

from __future__ import annotations

import pytest

from ibreeze.domain.review.aggregation import (
    FusedVerdict,
    ReportScore,
    compute_weight,
    confidence_ok,
    fuse_verdicts,
    rerun_decision,
)


def _score(verdict: str, weight: float, report_id: str = "r1") -> ReportScore:
    return ReportScore(report_id=report_id, verdict=verdict, weight=weight)


class TestFuseVerdicts:
    def test_any_non_pass_is_hard_veto(self) -> None:
        verdict = fuse_verdicts([_score("needs_changes", 0.5)], open_blocker_high_issues=0)
        assert verdict == FusedVerdict(verdict="needs_changes", confidence=1.0, hard_veto=True)

    def test_failed_among_passes_is_hard_veto(self) -> None:
        verdict = fuse_verdicts(
            [_score("pass", 0.5), _score("failed", 0.8)], open_blocker_high_issues=0
        )
        assert verdict.hard_veto
        assert verdict.verdict == "needs_changes"
        assert verdict.confidence == 1.0

    def test_open_blocker_high_is_hard_veto(self) -> None:
        verdict = fuse_verdicts([_score("pass", 0.5)], open_blocker_high_issues=1)
        assert verdict == FusedVerdict(verdict="needs_changes", confidence=1.0, hard_veto=True)

    def test_all_pass_independent_product(self) -> None:
        verdict = fuse_verdicts(
            [_score("pass", 0.5), _score("pass", 0.5), _score("pass", 0.5)],
            open_blocker_high_issues=0,
        )
        assert verdict.verdict == "pass"
        assert verdict.hard_veto is False
        assert verdict.confidence == pytest.approx(0.875)  # 1 - 0.5**3

    def test_empty_scores_have_zero_confidence(self) -> None:
        verdict = fuse_verdicts([], open_blocker_high_issues=0)
        assert verdict.verdict == "pass"
        assert verdict.confidence == 0.0

    def test_single_high_weight_pass(self) -> None:
        verdict = fuse_verdicts([_score("pass", 0.9)], open_blocker_high_issues=0)
        assert verdict.confidence == pytest.approx(0.9)


class TestComputeWeight:
    def test_cold_start_default(self) -> None:
        assert compute_weight(None) == 0.5
        assert compute_weight({"sample_count": 4, "accuracy": 0.99}) == 0.5

    def test_clamps_low_accuracy_floor(self) -> None:
        assert compute_weight({"sample_count": 5, "accuracy": 0.1}) == 0.30

    def test_clamps_high_accuracy_ceiling(self) -> None:
        assert compute_weight({"sample_count": 5, "accuracy": 0.99}) == 0.95

    def test_rounds_to_three_places(self) -> None:
        assert compute_weight({"sample_count": 6, "accuracy": 0.8766}) == pytest.approx(0.877)


class TestConfidenceOk:
    def test_hard_veto_is_always_ok(self) -> None:
        assert confidence_ok(FusedVerdict("needs_changes", 1.0, True), threshold=0.9) is True

    def test_confidence_threshold(self) -> None:
        assert confidence_ok(FusedVerdict("pass", 0.8, False), threshold=0.7) is True
        assert confidence_ok(FusedVerdict("pass", 0.6, False), threshold=0.7) is False


class TestRerunDecision:
    def _decide(self, verdict: FusedVerdict, **overrides: object) -> str:
        kwargs = {
            "current_round": 1,
            "review_rounds": 2,
            "pending_current_round": 0,
            "threshold": 0.7,
        }
        kwargs.update(overrides)
        return rerun_decision(verdict, **kwargs)

    def test_hard_veto_blocks(self) -> None:
        assert self._decide(FusedVerdict("needs_changes", 1.0, True)) == "blocked"

    def test_waits_for_quorum_before_fusing(self) -> None:
        assert self._decide(FusedVerdict("pass", 0.9, False), pending_current_round=1) == "wait_quorum"

    def test_high_confidence_passes(self) -> None:
        assert self._decide(FusedVerdict("pass", 0.9, False)) == "pass"

    def test_exhausted_rounds(self) -> None:
        assert (
            self._decide(FusedVerdict("pass", 0.5, False), current_round=2, review_rounds=2)
            == "exhausted"
        )

    def test_low_confidence_reruns(self) -> None:
        assert self._decide(FusedVerdict("pass", 0.5, False)) == "rerun"
