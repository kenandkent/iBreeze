"""Deterministic department responsibility scoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class DepartmentResponsibilityProfile:
    department_id: str
    responsibility_key: str
    accepted_task_types: frozenset[str]
    capability_tags: frozenset[str]
    deliverable_types: frozenset[str]
    quality_gates: frozenset[str]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DepartmentCandidate:
    department_id: str
    responsibility_key: str
    score: float
    matched_capabilities: tuple[str, ...]
    matched_deliverables: tuple[str, ...]
    matched_quality_gates: tuple[str, ...]


def _coverage(required: frozenset[str], available: frozenset[str]) -> float:
    if not required:
        return 1.0
    return len(required & available) / len(required)


def match_departments(
    profiles: list[DepartmentResponsibilityProfile],
    *,
    task_type: str,
    required_capabilities: frozenset[str],
    required_deliverables: frozenset[str],
    required_quality_gates: frozenset[str],
) -> list[DepartmentCandidate]:
    scored: list[tuple[DepartmentCandidate, datetime]] = []
    for profile in profiles:
        task_match = float(task_type in profile.accepted_task_types)
        capability = _coverage(
            required_capabilities,
            profile.capability_tags,
        )
        deliverable = _coverage(
            required_deliverables,
            profile.deliverable_types,
        )
        quality = _coverage(
            required_quality_gates,
            profile.quality_gates,
        )
        score = 40 * task_match + 30 * capability + 20 * deliverable + 10 * quality
        if score < 60:
            continue
        scored.append(
            (
                DepartmentCandidate(
                    department_id=profile.department_id,
                    responsibility_key=profile.responsibility_key,
                    score=round(score, 6),
                    matched_capabilities=tuple(
                        sorted(required_capabilities & profile.capability_tags)
                    ),
                    matched_deliverables=tuple(
                        sorted(required_deliverables & profile.deliverable_types)
                    ),
                    matched_quality_gates=tuple(
                        sorted(required_quality_gates & profile.quality_gates)
                    ),
                ),
                profile.created_at,
            )
        )
    scored.sort(
        key=lambda item: (
            -item[0].score,
            item[1],
            item[0].department_id,
        )
    )
    return [candidate for candidate, _ in scored]
