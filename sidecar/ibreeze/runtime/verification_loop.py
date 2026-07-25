"""Product verification with fix cycles."""

from __future__ import annotations

from typing import Any

MAX_FIX_ATTEMPTS = 5


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

        proc_info = await supervisor.start(
            f"{run_id}_verify_{attempts}",
            verification_command.split(),
            cwd=cwd,
        )
        wait_result = await supervisor.wait(
            f"{run_id}_verify_{attempts}",
            timeout=120,
        )

        results.append({
            "attempt": attempts,
            "exit_code": wait_result.get("exit_code"),
            "output_preview": wait_result.get("stdout_preview", "")[:1000],
        })

        if wait_result.get("exit_code") == 0:
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
