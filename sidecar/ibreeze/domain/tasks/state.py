from __future__ import annotations

from types import MappingProxyType

EMPLOYEE_TASK_TRANSITIONS: MappingProxyType[str, frozenset[str]] = MappingProxyType(
    {
        "assigned": frozenset({"ready", "waiting_resource", "cancelled", "failed"}),
        "ready": frozenset({"running", "waiting_resource", "cancelled", "failed"}),
        "running": frozenset({"submitted", "waiting_resource", "cancelled", "failed"}),
        "submitted": frozenset({"peer_reviewing", "changes_requested", "cancelled", "failed"}),
        "peer_reviewing": frozenset({"accepted", "changes_requested", "cancelled", "failed"}),
        "changes_requested": frozenset({"ready"}),
        "waiting_resource": frozenset({"assigned", "ready", "running"}),
        "accepted": frozenset(),
        "cancelled": frozenset(),
        "failed": frozenset(),
    }
)

DEPARTMENT_TASK_TRANSITIONS: MappingProxyType[str, frozenset[str]] = MappingProxyType(
    {
        "draft": frozenset({"checking_resources", "cancelled", "failed"}),
        "checking_resources": frozenset(
            {
                "ready",
                "waiting_dependency",
                "waiting_resource",
                "waiting_permission",
                "cancelled",
                "failed",
            }
        ),
        "ready": frozenset(
            {
                "executing",
                "waiting_dependency",
                "waiting_resource",
                "waiting_permission",
                "cancelled",
                "failed",
            }
        ),
        "executing": frozenset(
            {
                "reviewing",
                "waiting_dependency",
                "waiting_resource",
                "waiting_permission",
                "cancelled",
                "failed",
            }
        ),
        "reviewing": frozenset({"completed", "fixing", "cancelled", "failed"}),
        "fixing": frozenset({"reviewing", "cancelled", "failed"}),
        "waiting_dependency": frozenset({"checking_resources", "ready", "executing"}),
        "waiting_resource": frozenset({"checking_resources", "ready", "executing"}),
        "waiting_permission": frozenset({"checking_resources", "ready", "executing"}),
        "completed": frozenset(),
        "cancelled": frozenset(),
        "failed": frozenset(),
    }
)

COMPANY_TASK_TRANSITIONS: MappingProxyType[str, frozenset[str]] = MappingProxyType(
    {
        "draft": frozenset({"analyzing", "cancelled", "failed"}),
        "analyzing": frozenset(
            {
                "awaiting_user_confirmation",
                "waiting_resource",
                "revision_requested",
                "cancelled",
                "failed",
            }
        ),
        "awaiting_user_confirmation": frozenset(
            {
                "approved",
                "revision_requested",
                "rejected",
                "cancelled",
                "failed",
            }
        ),
        "revision_requested": frozenset({"analyzing", "cancelled", "failed"}),
        "rejected": frozenset(),
        "approved": frozenset({"dispatching", "cancelled", "failed"}),
        "dispatching": frozenset(
            {
                "checking_resources",
                "waiting_dependency",
                "waiting_resource",
                "waiting_permission",
                "cancelled",
                "failed",
            }
        ),
        "checking_resources": frozenset(
            {
                "executing",
                "waiting_dependency",
                "waiting_resource",
                "waiting_permission",
                "cancelled",
                "failed",
            }
        ),
        "executing": frozenset(
            {
                "reviewing",
                "waiting_dependency",
                "waiting_resource",
                "waiting_permission",
                "paused",
                "cancelled",
                "failed",
            }
        ),
        "reviewing": frozenset({"final_review", "fixing", "cancelled", "failed"}),
        "fixing": frozenset({"reviewing", "cancelled", "failed"}),
        "final_review": frozenset({"completed", "cancelled", "failed"}),
        "waiting_dependency": frozenset({"checking_resources", "executing", "reviewing", "cancelled", "failed"}),
        "waiting_resource": frozenset({"checking_resources", "executing", "reviewing", "cancelled", "failed"}),
        "waiting_permission": frozenset({"checking_resources", "executing", "reviewing", "cancelled", "failed"}),
        "paused": frozenset({"executing", "cancelled", "failed"}),
        "cancelling": frozenset({"cancelled", "failed"}),
        "completed": frozenset(),
        "cancelled": frozenset(),
        "failed": frozenset(),
    }
)

EMPLOYEE_TASK_ALL_EDGES: frozenset[tuple[str, str]] = frozenset(
    (src, tgt) for src, targets in EMPLOYEE_TASK_TRANSITIONS.items() for tgt in targets
)

DEPARTMENT_TASK_ALL_EDGES: frozenset[tuple[str, str]] = frozenset(
    (src, tgt) for src, targets in DEPARTMENT_TASK_TRANSITIONS.items() for tgt in targets
)

COMPANY_TASK_ALL_EDGES: frozenset[tuple[str, str]] = frozenset(
    (src, tgt) for src, targets in COMPANY_TASK_TRANSITIONS.items() for tgt in targets
)
