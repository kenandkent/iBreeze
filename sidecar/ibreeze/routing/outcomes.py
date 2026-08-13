"""Outcome projection and local calibration for routing deployments."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5


@dataclass(frozen=True, slots=True)
class RouteOutcome:
    route_decision_id: str
    outcome_type: str
    source_id: str
    score: Decimal
    label: str


class RouteOutcomeProjector:
    """Append-only projection used by review/completion transactions.

    The projector deliberately accepts a transaction-bound connection.  It
    never opens a writer or derives a random source id, so event replays are
    naturally idempotent through the repository unique key.
    """

    def __init__(self, repository: Any | None = None) -> None:
        if repository is None:
            from ibreeze.routing.repository import RoutingRepository

            repository = RoutingRepository()
        self.repository = repository

    async def append(
        self,
        db: Any,
        *,
        route_decision_id: str,
        company_id: str,
        outcome_type: str,
        source_id: str,
        event: str,
        has_blocker: bool = False,
    ) -> bool:
        outcome = project_outcome(route_decision_id, outcome_type, source_id, event, has_blocker=has_blocker)
        return await self.repository.record_outcome(
            db,
            outcome_id=f"{route_decision_id}:{outcome_type}:{source_id}",
            route_decision_id=outcome.route_decision_id,
            company_id=company_id,
            outcome_type=outcome.outcome_type,
            source_id=outcome.source_id,
            score=float(outcome.score),
            label=outcome.label,
        )


def stable_tool_source_id(run_id: str, turn_index: int, tool_call_id: str) -> str:
    """Derive a repeatable UUID for one tool result attribution.

    A turn may contain more than one tool call, so ``run_id:turn_index`` alone
    would incorrectly collapse distinct outcomes. UUIDv5 keeps the source ID
    stable across Outbox replay without storing tool arguments or results.
    """
    normalized_run_id = str(UUID(run_id))
    if turn_index <= 0 or not tool_call_id or ":" in tool_call_id:
        raise ValueError("ROUTE_OUTCOME_SOURCE_INVALID")
    return str(uuid5(NAMESPACE_URL, f"ibreeze:tool:{normalized_run_id}:{turn_index}:{tool_call_id}"))


def outcome_for(event: str, *, has_blocker: bool = False) -> tuple[Decimal, str]:
    mapping = {
        "tool_verified": (Decimal("1"), "tool_verified"),
        "tool_rejected": (Decimal("0"), "tool_rejected"),
        "verification_passed": (Decimal("1"), "verification_passed"),
        "verification_failed": (Decimal("0"), "verification_failed"),
        "review_passed": (Decimal("1"), "review_passed"),
        "review_needs_changes": (Decimal("0.4"), "review_needs_changes"),
        "review_failed": (Decimal("0"), "review_failed"),
        "task_succeeded": (Decimal("1"), "task_succeeded"),
        "task_failed": (Decimal("0"), "task_failed"),
        "task_timed_out": (Decimal("0"), "task_failed"),
    }
    if event == "review_passed" and has_blocker:
        return Decimal("0"), "review_failed"
    try:
        return mapping[event]
    except KeyError:
        raise ValueError("ROUTE_OUTCOME_EVENT_INVALID") from None


def project_outcome(route_decision_id: str, outcome_type: str, source_id: str, event: str, *, has_blocker: bool = False) -> RouteOutcome:
    if not _is_stable_source_id(source_id):
        raise ValueError("ROUTE_OUTCOME_SOURCE_INVALID")
    score, label = outcome_for(event, has_blocker=has_blocker)
    return RouteOutcome(route_decision_id, outcome_type, source_id, score, label)


def _is_stable_source_id(source_id: str) -> bool:
    if not source_id or source_id.startswith("random:"):
        return False
    try:
        UUID(source_id)
        return True
    except ValueError:
        pass
    parts = source_id.split(":")
    if len(parts) != 2 or not parts[0]:
        return False
    try:
        UUID(parts[0])
        return int(parts[1]) > 0
    except (ValueError, TypeError):
        return False


def local_calibration(
    samples: Iterable[tuple[float | Decimal, float | Decimal]], *, catalog_quality_prior: Decimal | float, minimum_samples: int = 30
) -> Decimal:
    values = list(samples)
    if len(values) < minimum_samples:
        return Decimal("0")
    prior = Decimal(str(catalog_quality_prior))
    total = sum((Decimal(str(score)) for score, _prior in values), Decimal("0"))
    quality = (total + Decimal("5") * prior) / (Decimal(len(values)) + Decimal("5"))
    value = quality - prior
    return min(Decimal("0.20"), max(Decimal("-0.20"), value))


def calibration_for_purpose(
    samples_by_purpose: Mapping[str, Iterable[tuple[float | Decimal, float | Decimal]]],
    *,
    purpose: str,
    catalog_quality_prior: Decimal | float,
) -> Decimal:
    """Calculate a deployment calibration using a purpose bucket first.

    A purpose bucket with fewer than 30 samples deliberately falls back to
    the deployment's global samples.  This keeps a newly introduced purpose
    from changing routing based on a tiny local sample while still allowing
    mature history to influence the score.
    """
    buckets = {key: list(values) for key, values in samples_by_purpose.items()}
    purpose_samples = buckets.get(purpose, [])
    if len(purpose_samples) >= 30:
        return local_calibration(purpose_samples, catalog_quality_prior=catalog_quality_prior)
    global_samples = [sample for values in buckets.values() for sample in values]
    return local_calibration(global_samples, catalog_quality_prior=catalog_quality_prior)


async def load_local_calibrations(
    read_pool: Any | None,
    *,
    company_id: str,
    purpose: str,
    candidate_priors: Mapping[str, Decimal | float],
) -> dict[str, Decimal]:
    """Load outcome samples for the winning attempt of each prior Decision.

    Outcome rows are attached to a Decision, while the last successful
    physical Attempt identifies the Deployment that produced the result.  No
    prompt, candidate body, credential reference, or hash is read here.
    """
    query_all = getattr(read_pool, "query_all", None)
    if read_pool is None or not callable(query_all) or not candidate_priors:
        return {str(candidate_id): Decimal("0") for candidate_id in candidate_priors}
    rows = await query_all(
        """
        WITH successful_attempts AS (
            SELECT route_decision_id, candidate_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY route_decision_id ORDER BY attempt_sequence DESC
                   ) AS rank
            FROM route_attempts
            WHERE company_id=? AND status='succeeded'
        )
        SELECT a.candidate_id, r.run_purpose, o.score
        FROM successful_attempts a
        JOIN route_decisions d ON d.id=a.route_decision_id AND d.company_id=?
        JOIN route_outcomes o ON o.route_decision_id=d.id AND o.company_id=d.company_id
        JOIN agent_runs r ON r.id=d.run_id AND r.company_id=d.company_id
        WHERE a.rank=1
        """,
        (company_id, company_id),
    )
    samples: dict[str, dict[str, list[tuple[float, float]]]] = {}
    for row in rows:
        candidate_id = str(row.get("candidate_id", ""))
        if candidate_id not in candidate_priors:
            continue
        bucket = str(row.get("run_purpose", ""))
        samples.setdefault(candidate_id, {}).setdefault(bucket, []).append((float(row["score"]), 0.0))
    return {
        candidate_id: calibration_for_purpose(
            samples.get(candidate_id, {}),
            purpose=purpose,
            catalog_quality_prior=prior,
        )
        for candidate_id, prior in candidate_priors.items()
    }
