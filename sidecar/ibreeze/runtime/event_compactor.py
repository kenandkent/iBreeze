"""Event compaction and transcript generation for agent runs."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def compact_events(db: Any, run_id: str) -> dict[str, Any]:
    """Compact events for a run into a human-readable transcript.

    Reads all ``agent_run_events`` ordered by ``sequence``, builds a
    transcript, then writes a ``compaction.marker`` event so future
    readers can fast-forward past the compacted range.
    """
    cursor = await db.execute(
        "SELECT event_id, sequence, event_type, payload_json, trace_id, occurred_at "
        "FROM agent_run_events WHERE run_id = ? ORDER BY sequence ASC",
        (run_id,),
    )
    events = await cursor.fetchall()
    if not events:
        return {"transcript": "", "event_count": 0}

    transcript_parts: list[str] = []
    for event in events:
        event_type: str = event["event_type"]
        raw = event["payload_json"]
        payload: dict[str, Any] = json.loads(raw) if raw else {}

        if event_type == "run.started":
            transcript_parts.append(
                f"[Run Started] Agent: {payload.get('agent_id', 'unknown')}"
            )
        elif event_type == "run.completed":
            transcript_parts.append(f"[Run Completed] {payload.get('summary', '')}")
        elif event_type == "run.failed":
            transcript_parts.append(f"[Run Failed] {payload.get('error', 'unknown')}")
        elif event_type == "model.output.done":
            transcript_parts.append(f"[Model Output] {payload.get('output', '')[:500]}")
        elif event_type.startswith("tool."):
            tool_name = payload.get("tool", "unknown")
            if event_type == "tool.completed":
                transcript_parts.append(f"[Tool: {tool_name}] Completed")
            elif event_type == "tool.failed":
                transcript_parts.append(
                    f"[Tool: {tool_name}] Failed: {payload.get('error', '')}"
                )
        elif event_type.startswith("approval."):
            transcript_parts.append(
                f"[Approval {payload.get('status', '')}] Tool: {payload.get('tool', '')}"
            )

    transcript = "\n".join(transcript_parts)

    # Write a compaction marker so future replays can skip raw events.
    now = _now()
    next_seq = (events[-1]["sequence"] if events else 0) + 1
    await db.execute(
        (
            "INSERT INTO agent_run_events "
            "(run_id, event_id, sequence, event_type, payload_json, trace_id, occurred_at) "
            "VALUES (?, ?, ?, 'compaction.marker', ?, ?, ?)"
        ),
        (
            run_id,
            _id(),
            next_seq,
            json.dumps({"transcript_preview": transcript[:1000]}, ensure_ascii=False),
            _id(),
            now,
        ),
    )
    return {
        "transcript": transcript,
        "event_count": len(events),
        "compacted_at": now,
    }
