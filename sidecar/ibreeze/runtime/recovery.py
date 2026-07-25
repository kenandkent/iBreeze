"""Run crash recovery — reconcile stale agent runs after restart."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# Non-terminal, non-waiting statuses that indicate a run was interrupted.
_STALE_STATUSES = ("queued", "probing", "starting", "running", "verifying", "retrying")

_RECOVERY_MESSAGE_PREFIX = "Crash recovery"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def recover_stale_runs(db: Any) -> dict[str, Any]:
    """Recover runs that were interrupted by a crash.

    Runs in a non-terminal, non-waiting state are marked ``failed`` with an
    explanatory ``failure_code`` so the UI and downstream consumers can
    distinguish them from normal failures.
    """
    now = _now()

    placeholders = ",".join("?" for _ in _STALE_STATUSES)
    cursor = await db.execute(
        f"SELECT id, status FROM agent_runs WHERE status IN ({placeholders})",
        _STALE_STATUSES,
    )
    stale_runs = await cursor.fetchall()

    recovered = 0
    for run in stale_runs:
        run_id = run["id"]
        status = run["status"]

        await db.execute(
            (
                "UPDATE agent_runs "
                "SET status = 'failed', "
                "    failure_code = ?, "
                "    updated_at = ? "
                "WHERE id = ?"
            ),
            (f"{_RECOVERY_MESSAGE_PREFIX}: run was '{status}' at crash time", now, run_id),
        )
        recovered += 1

    if recovered:
        await db.commit()

    return {"recovered": recovered, "checked": len(stale_runs)}
