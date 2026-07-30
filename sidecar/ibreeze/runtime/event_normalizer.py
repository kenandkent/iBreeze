"""Event normalization for 14 standard runtime event types.

14.6 标准事件：
run.started / run.completed / run.failed / run.cancelled
model.output.delta / model.output.done
tool.requested / tool.started / tool.completed / tool.failed
checkpoint.created / checkpoint.restored
approval.requested / approval.resolved
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


EVENT_TYPES = frozenset(
    {
        "run.started",
        "run.completed",
        "run.failed",
        "run.cancelled",
        "model.output.delta",
        "model.output.done",
        "tool.requested",
        "tool.started",
        "tool.completed",
        "tool.failed",
        "checkpoint.created",
        "checkpoint.restored",
        "approval.requested",
        "approval.resolved",
    }
)


def normalize_event(
    raw_event: dict[str, Any],
    run_id: str,
    sequence: int,
    *,
    trace_id: str = "",
) -> dict[str, Any]:
    """Normalize a raw event into the standard event format."""
    event_type = raw_event.get("type", "unknown")
    now = _now()

    return {
        "run_id": run_id,
        "event_id": _id(),
        "sequence": sequence,
        "event_type": event_type,
        "payload_json": json.dumps(raw_event.get("data", {}), ensure_ascii=False),
        "native_event_json": json.dumps(raw_event, ensure_ascii=False),
        "trace_id": trace_id or _id(),
        "occurred_at": now,
    }


def create_run_started(
    run_id: str,
    sequence: int,
    *,
    employee_id: str,
    model_id: str,
    trace_id: str = "",
) -> dict[str, Any]:
    return normalize_event(
        {"type": "run.started", "data": {"employee_id": employee_id, "model_id": model_id}},
        run_id,
        sequence,
        trace_id=trace_id,
    )


def create_run_completed(
    run_id: str,
    sequence: int,
    *,
    summary: str,
    trace_id: str = "",
) -> dict[str, Any]:
    return normalize_event(
        {"type": "run.completed", "data": {"summary": summary}},
        run_id,
        sequence,
        trace_id=trace_id,
    )


def create_run_failed(
    run_id: str,
    sequence: int,
    *,
    error: str,
    trace_id: str = "",
) -> dict[str, Any]:
    return normalize_event(
        {"type": "run.failed", "data": {"error": error}},
        run_id,
        sequence,
        trace_id=trace_id,
    )


def create_run_cancelled(
    run_id: str,
    sequence: int,
    *,
    reason: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    return normalize_event(
        {"type": "run.cancelled", "data": {"reason": reason}},
        run_id,
        sequence,
        trace_id=trace_id,
    )


def create_model_delta(
    run_id: str,
    sequence: int,
    *,
    delta: str,
    trace_id: str = "",
) -> dict[str, Any]:
    return normalize_event(
        {"type": "model.output.delta", "data": {"delta": delta}},
        run_id,
        sequence,
        trace_id=trace_id,
    )


def create_model_done(
    run_id: str,
    sequence: int,
    *,
    output: str,
    trace_id: str = "",
) -> dict[str, Any]:
    return normalize_event(
        {"type": "model.output.done", "data": {"output": output}},
        run_id,
        sequence,
        trace_id=trace_id,
    )


def create_tool_event(
    run_id: str,
    sequence: int,
    *,
    tool_name: str,
    status: str,
    result: Any = None,
    trace_id: str = "",
) -> dict[str, Any]:
    if status not in ("requested", "started", "completed", "failed"):
        raise ValueError(f"Invalid tool status: {status}")
    return normalize_event(
        {"type": f"tool.{status}", "data": {"tool": tool_name, "result": result}},
        run_id,
        sequence,
        trace_id=trace_id,
    )


def create_checkpoint(
    run_id: str,
    sequence: int,
    *,
    checkpoint_id: str,
    restored: bool = False,
    trace_id: str = "",
) -> dict[str, Any]:
    event_type = "checkpoint.restored" if restored else "checkpoint.created"
    return normalize_event(
        {"type": event_type, "data": {"checkpoint_id": checkpoint_id}},
        run_id,
        sequence,
        trace_id=trace_id,
    )


def create_approval_event(
    run_id: str,
    sequence: int,
    *,
    tool_name: str,
    status: str,
    trace_id: str = "",
) -> dict[str, Any]:
    if status not in ("requested", "resolved"):
        raise ValueError(f"Invalid approval status: {status}")
    return normalize_event(
        {"type": f"approval.{status}", "data": {"tool": tool_name}},
        run_id,
        sequence,
        trace_id=trace_id,
    )


def create_compacted_event(
    run_id: str,
    sequence: int,
    *,
    original_events: list[Any],
    compacted_data: dict[str, Any],
    trace_id: str = "",
) -> dict[str, Any]:
    return normalize_event(
        {"type": "model.output.compacted", "data": {"original_count": len(original_events), **compacted_data}},
        run_id,
        sequence,
        trace_id=trace_id,
    )


def create_tool_approved_event(
    run_id: str,
    sequence: int,
    *,
    tool_name: str,
    tool_args: dict[str, Any],
    trace_id: str = "",
) -> dict[str, Any]:
    return normalize_event(
        {"type": "tool.approved", "data": {"tool": tool_name, "args": tool_args}},
        run_id,
        sequence,
        trace_id=trace_id,
    )


def create_tool_rejected_event(
    run_id: str,
    sequence: int,
    *,
    tool_name: str,
    reason: str,
    trace_id: str = "",
) -> dict[str, Any]:
    return normalize_event(
        {"type": "tool.rejected", "data": {"tool": tool_name, "reason": reason}},
        run_id,
        sequence,
        trace_id=trace_id,
    )


def create_workspace_changed_event(
    run_id: str,
    sequence: int,
    *,
    changes: list[Any],
    trace_id: str = "",
) -> dict[str, Any]:
    return normalize_event(
        {"type": "workspace.changed", "data": {"changes": changes}},
        run_id,
        sequence,
        trace_id=trace_id,
    )


def create_verification_started_event(
    run_id: str,
    sequence: int,
    *,
    target_run_id: str,
    trace_id: str = "",
) -> dict[str, Any]:
    return normalize_event(
        {"type": "verification.started", "data": {"target_run_id": target_run_id}},
        run_id,
        sequence,
        trace_id=trace_id,
    )


def create_verification_completed_event(
    run_id: str,
    sequence: int,
    *,
    verdict: str,
    issues: list[Any],
    trace_id: str = "",
) -> dict[str, Any]:
    return normalize_event(
        {"type": "verification.completed", "data": {"verdict": verdict, "issues": issues}},
        run_id,
        sequence,
        trace_id=trace_id,
    )


async def store_event(db: Any, event: dict[str, Any]) -> str:
    """Store a normalized event in the database."""
    await db.execute(
        """INSERT INTO agent_run_events
        (run_id, event_id, sequence, event_type, payload_json,
         native_event_json, trace_id, occurred_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event["run_id"],
            event["event_id"],
            event["sequence"],
            event["event_type"],
            event["payload_json"],
            event.get("native_event_json"),
            event["trace_id"],
            event["occurred_at"],
        ),
    )
    return event["event_id"]  # type: ignore[no-any-return]
