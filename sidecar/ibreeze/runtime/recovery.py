"""Crash recovery for Agent Runs and intelligent-routing state.

Recovery is deliberately conservative.  A restarted Sidecar has no proof that
an accepted/streaming Provider request did not already produce output, so it
marks the local Attempt failed and never replays it automatically.
"""

from __future__ import annotations

from collections.abc import Iterable
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
        f"SELECT id, company_id, status, version FROM agent_runs WHERE status IN ({placeholders})",
        _STALE_STATUSES,
    )
    stale_runs = await cursor.fetchall()

    recovered = 0
    for run in stale_runs:
        run_id = str(run["id"])
        company_id = str(run["company_id"])
        status = str(run["status"])
        version = int(run["version"])

        cursor = await db.execute(
            """UPDATE agent_runs
               SET status='failed', failure_code=?, completed_at=?,
                   process_pid=NULL, process_group_id=NULL, process_started_at=NULL,
                   updated_at=?, version=version+1
               WHERE id=? AND company_id=? AND status=? AND version=?""",
            (
                f"{_RECOVERY_MESSAGE_PREFIX}: run was '{status}' at crash time",
                now,
                now,
                run_id,
                company_id,
                status,
                version,
            ),
        )
        if cursor.rowcount != 1:
            continue

        # A crashed process cannot own a lease or leave a queue item eligible
        # for a second execution.  The updates are idempotent and are part of
        # the same WriteQueue transaction as the Run transition.
        await db.execute(
            """UPDATE runtime_queue
               SET status='cancelled'
               WHERE run_id=? AND company_id=? AND status IN ('ready','leased')""",
            (run_id, company_id),
        )
        await db.execute("DELETE FROM runtime_leases WHERE run_id=? AND company_id=?", (run_id, company_id))

        # Healthy production databases contain the company row and therefore
        # receive the normal durable run.failed event.  The conditional keeps
        # the low-level recovery helper usable for legacy/imported test rows
        # that intentionally omit aggregate fixtures.
        company_cursor = await db.execute("SELECT 1 FROM companies WHERE id=?", (company_id,))
        if await company_cursor.fetchone() is not None:
            from ibreeze.runtime.run_executor import _write_event

            await _write_event(
                db,
                company_id=company_id,
                run_id=run_id,
                event_type="run.failed",
                payload={
                    "company_id": company_id,
                    "aggregate_id": run_id,
                    "version": version + 1,
                    "from_state": status,
                    "to_state": "failed",
                    "failure_code": f"{_RECOVERY_MESSAGE_PREFIX}: run was '{status}' at crash time",
                },
            )
        recovered += 1

    return {"recovered": recovered, "checked": len(stale_runs)}


async def cleanup_expired_health(db: Any, *, now: str | None = None) -> int:
    """Delete only expired *ready* health rows before accepting new Runs.

    Active benches and ``credential_invalid`` rows are retained for audit and
    capability-gate exclusion.  The operation is safe to repeat on restart.
    """

    effective_now = now or _now()
    cursor = await db.execute(
        """DELETE FROM deployment_health
           WHERE availability_state='ready'
             AND benched_until IS NOT NULL
             AND benched_until <= ?""",
        (effective_now,),
    )
    return int(cursor.rowcount)


async def reconcile_interrupted_routing(
    db: Any,
    *,
    active_attempt_ids: Iterable[str] | None = None,
) -> dict[str, int]:
    """Reconcile Route Decision/Attempt rows left by a Sidecar crash.

    ``active_attempt_ids`` is an optional set obtained from a trusted Rust
    Broker session.  At normal startup it is omitted because the authenticated
    session has not been established yet; in that case every non-terminal
    Attempt is conservatively failed and never replayed.  A caller that has a
    verified Rust active set may preserve those attempts and their executing
    Decisions for the reconnect path.
    """

    active = {str(value) for value in (active_attempt_ids or ())}
    now = _now()
    failed_attempts = 0
    preserved_attempts = 0

    cursor = await db.execute(
        """SELECT id, route_decision_id, status
           FROM route_attempts
           WHERE status IN ('created','accepted','streaming')"""
    )
    attempts = await cursor.fetchall()
    for row in attempts:
        attempt_id = str(row["id"])
        if attempt_id in active:
            preserved_attempts += 1
            continue
        updated = await db.execute(
            """UPDATE route_attempts
               SET status='failed', failure_kind='TRANSPORT_TRANSIENT', completed_at=?
               WHERE id=? AND status IN ('created','accepted','streaming')""",
            (now, attempt_id),
        )
        failed_attempts += int(updated.rowcount)

    # A planned Decision has no accepted physical request and is safe to fail
    # directly.  An executing Decision is failed only when no verified Rust
    # Attempt remains active for it.
    planned = await db.execute(
        """UPDATE route_decisions
           SET status='failed', completed_at=?
           WHERE status='planned'""",
        (now,),
    )
    failed_planned = int(planned.rowcount)

    executing_cursor = await db.execute(
        """SELECT id FROM route_decisions WHERE status='executing'"""
    )
    executing = await executing_cursor.fetchall()
    failed_executing = 0
    for row in executing:
        decision_id = str(row["id"])
        if not active:
            active_cursor = None
        else:
            placeholders = ",".join("?" for _ in active)
            active_cursor = await db.execute(
                f"""SELECT 1 FROM route_attempts
                    WHERE route_decision_id=? AND status IN ('created','accepted','streaming')
                      AND id IN ({placeholders}) LIMIT 1""",
                (decision_id, *active),
            )
        if active_cursor is not None and await active_cursor.fetchone() is not None:
            continue
        updated = await db.execute(
            """UPDATE route_decisions
               SET status='failed', completed_at=?
               WHERE id=? AND status='executing'""",
            (now, decision_id),
        )
        failed_executing += int(updated.rowcount)

    return {
        "failed_attempts": failed_attempts,
        "preserved_attempts": preserved_attempts,
        "failed_planned_decisions": failed_planned,
        "failed_executing_decisions": failed_executing,
    }


async def reconcile_startup_state(db: Any) -> dict[str, Any]:
    """Run all local recovery steps in one startup WriteQueue transaction."""

    runs = await recover_stale_runs(db)
    routing = await reconcile_interrupted_routing(db)
    health = await cleanup_expired_health(db)
    return {"runs": runs, "routing": routing, "expired_health": health}
