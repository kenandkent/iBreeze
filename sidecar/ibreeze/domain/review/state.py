from __future__ import annotations

from types import MappingProxyType

ASSIGNMENT_TRANSITIONS: MappingProxyType[str, frozenset[str]] = MappingProxyType(
    {
        "assigned": frozenset({"in_review", "stale", "cancelled"}),
        "in_review": frozenset({"submitted", "stale", "cancelled"}),
        "submitted": frozenset({"stale"}),
        "stale": frozenset(),
        "cancelled": frozenset(),
    }
)

ISSUE_TRANSITIONS: MappingProxyType[str, frozenset[str]] = MappingProxyType(
    {
        "open": frozenset({"fixing", "rejected"}),
        "fixing": frozenset({"resolved"}),
        "resolved": frozenset({"verified", "fixing"}),
        "verified": frozenset({"closed", "fixing"}),
        "closed": frozenset(),
        "rejected": frozenset(),
    }
)

ASSIGNMENT_ALL_EDGES: frozenset[tuple[str, str]] = frozenset(
    (src, tgt) for src, targets in ASSIGNMENT_TRANSITIONS.items() for tgt in targets
)

ISSUE_ALL_EDGES: frozenset[tuple[str, str]] = frozenset((src, tgt) for src, targets in ISSUE_TRANSITIONS.items() for tgt in targets)
