"""Product verification with fix cycles."""

from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from typing import Any

MAX_FIX_ATTEMPTS = 5


async def _project_verification_outcome(
    db: Any,
    *,
    run_id: str,
    company_id: str,
    artifact_id: str,
    passed: bool,
) -> None:
    """Project each verification result onto the latest routing decision.

    Verification is intentionally best-effort for legacy/CLI runs: a run with
    no Route Decision still records its normal ``verification_results`` row.
    The lookup and projection use the caller's transaction-bound connection so
    an Outbox replay cannot create a second outcome for the same result.
    """
    cursor = await db.execute(
        """SELECT id FROM route_decisions
           WHERE company_id=? AND run_id=?
           ORDER BY turn_index DESC, id DESC LIMIT 1""",
        (company_id, run_id),
    )
    fetched = cursor.fetchone()
    row = await fetched if inspect.isawaitable(fetched) else fetched
    if row is None:
        return
    from ibreeze.routing.outcomes import RouteOutcomeProjector

    decision_id = row["id"] if hasattr(row, "keys") else row[0]
    await RouteOutcomeProjector().append(
        db,
        route_decision_id=str(decision_id),
        company_id=company_id,
        outcome_type="verification",
        source_id=artifact_id,
        event="verification_passed" if passed else "verification_failed",
    )


async def verify_and_fix(
    db: Any,
    *,
    run_id: str,
    company_id: str,
    artifact_id: str,
    verification_command: str,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Run verification command and attempt fixes up to MAX_FIX_ATTEMPTS.

    Each round:
    1. Execute *verification_command* via the process supervisor.
    2. Record the result as a ``verification_results`` row.
    3. On failure, emit a fix request back to the model (caller responsibility).
    4. Repeat until pass or MAX_FIX_ATTEMPTS exhausted.
    """
    from .process_supervisor import get_supervisor

    supervisor = get_supervisor()
    attempts = 0
    results: list[dict[str, Any]] = []

    while attempts < MAX_FIX_ATTEMPTS:
        attempts += 1

        await supervisor.start(
            f"{run_id}_verify_{attempts}",
            verification_command.split(),
            cwd=cwd,
        )
        wait_result = await supervisor.wait(
            f"{run_id}_verify_{attempts}",
            timeout=120,
        )

        results.append(
            {
                "attempt": attempts,
                "exit_code": wait_result.get("exit_code"),
                "output_preview": wait_result.get("stdout_preview", "")[:1000],
            }
        )

        verdict = "passed" if wait_result.get("exit_code") == 0 else "failed"
        now = datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
        import uuid as _uuid

        verification_id = str(_uuid.uuid4())

        await db.execute(
            """INSERT INTO verification_results
               (id, company_id, run_id, round_number, command_argv_json, exit_code,
                status, started_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                verification_id,
                company_id,
                run_id,
                attempts,
                json.dumps(verification_command.split()),
                wait_result.get("exit_code", -1),
                verdict,
                now,
                now,
            ),
        )

        await _project_verification_outcome(
            db,
            run_id=run_id,
            company_id=company_id,
            artifact_id=artifact_id,
            passed=verdict == "passed",
        )

        if verdict == "passed":
            return {
                "status": "passed",
                "attempts": attempts,
                "results": results,
            }

    return {
        "status": "failed",
        "attempts": attempts,
        "results": results,
    }
