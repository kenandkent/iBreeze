"""Run executor — consumer loop that dequeues and executes agent runs.

Connects scheduler → CLI adapters / ModelRuntime → feedback to task states.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from ibreeze.runtime.cli import create_adapter
from ibreeze.runtime.process_supervisor import get_supervisor
from ibreeze.runtime.scheduler import (
    acquire_lease,
    dequeue_next,
    heartbeat_lease,
    release_lease,
    update_fairness,
)

logger = logging.getLogger("ibreeze.run_executor")

_TERMINAL_RUN = {"succeeded", "cancelled", "timed_out", "failed", "lost"}


def _now() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def _write_event(
    db: Any, *, company_id: str, run_id: str, event_type: str, payload: dict,
) -> None:
    import uuid
    event_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO agent_run_events
           (event_id, run_id, event_type, payload_json, sequence, trace_id, occurred_at)
           VALUES (?,?,?,?, COALESCE(
               (SELECT MAX(sequence)+1 FROM agent_run_events WHERE run_id=?), 1
           ),?,?)""",
        (event_id, run_id, event_type, json.dumps(payload), run_id, str(uuid.uuid4()), _now()),
    )


async def execute_single_run(
    db: Any,
    run_id: str,
    company_id: str,
) -> dict[str, Any]:
    """Execute a single dequeued run. Called by the consumer loop."""
    now = _now()
    supervisor = get_supervisor()

    # Fetch run details
    run_row = await (await db.execute(
        """SELECT id, company_id, adapter_type, run_spec_json, employee_id,
                  process_pid, status
           FROM agent_runs WHERE id=? AND company_id=?""",
        (run_id, company_id),
    )).fetchone()
    if run_row is None:
        return {"error": "RUN_NOT_FOUND"}

    if run_row["status"] in _TERMINAL_RUN:
        return {"error": "RUN_ALREADY_TERMINAL"}

    run = dict(run_row)
    spec = json.loads(run["run_spec_json"])
    adapter_type = run["adapter_type"]
    prompt = spec.get("prompt", "")

    # Transition: queued → probing → starting → running
    await db.execute(
        """UPDATE agent_runs SET status='probing', updated_at=?, version=version+1
           WHERE id=? AND company_id=?""",
        (now, run_id, company_id),
    )
    await _write_event(db, company_id=company_id, run_id=run_id,
                       event_type="run_probing", payload={"adapter_type": adapter_type})

    # Probe adapter availability
    probe_ok = await _probe_adapter(adapter_type)
    if not probe_ok:
        await _fail_run(db, run_id, company_id, "ADAPTER_UNAVAILABLE")
        return {"error": "ADAPTER_UNAVAILABLE"}

    await db.execute(
        """UPDATE agent_runs SET status='starting', updated_at=?, version=version+1
           WHERE id=? AND company_id=?""",
        (now, run_id, company_id),
    )

    # Execute via CLI adapter or ModelRuntime
    try:
        if adapter_type in ("agent_cli", "codex_cli", "claude_code", "opencode"):
            result = await _execute_cli(run_id, spec, adapter_type)
        elif adapter_type == "api_model":
            result = await _execute_model(run_id, spec)
        else:
            await _fail_run(db, run_id, company_id, "UNKNOWN_ADAPTER_TYPE")
            return {"error": "UNKNOWN_ADAPTER_TYPE"}
    except Exception as exc:
        logger.exception("Run %s failed with exception", run_id)
        await _fail_run(db, run_id, company_id, "EXECUTION_ERROR")
        return {"error": "EXECUTION_ERROR", "detail": str(exc)}

    # Update run status
    success = result.get("exit_code", -1) == 0
    final_status = "succeeded" if success else "failed"
    completed_at = _now()

    await db.execute(
        """UPDATE agent_runs
           SET status=?, completed_at=?, exit_code=?, failure_code=?,
               updated_at=?, version=version+1
           WHERE id=? AND company_id=?""",
        (final_status, completed_at, result.get("exit_code", -1),
         None if success else "AGENT_FAILED", completed_at, run_id, company_id),
    )
    await _write_event(db, company_id=company_id, run_id=run_id,
                       event_type=f"run_{final_status}",
                       payload={"exit_code": result.get("exit_code", -1)})

    # Feedback to task states
    await _feedback_to_tasks(db, run_id, company_id, success)

    # Update fairness
    await update_fairness(db, company_id)

    return {"run_id": run_id, "status": final_status}


async def _probe_adapter(adapter_type: str) -> bool:
    """Check if the CLI adapter is available on this machine."""
    from ibreeze.runtime.cli import probe_agent, AdapterName
    mapping = {"codex_cli": "codex_cli", "claude_code": "claude_code",
               "opencode": "opencode", "agent_cli": "codex_cli"}
    name = mapping.get(adapter_type)
    if name is None:
        return adapter_type == "api_model"
    try:
        probe = await probe_agent(name, timeout_seconds=5)
        return probe.available
    except Exception:
        return False


async def _execute_cli(
    run_id: str, spec: dict, adapter_type: str,
) -> dict[str, Any]:
    """Execute a CLI adapter run."""
    from ibreeze.runtime.process_supervisor import get_supervisor
    supervisor = get_supervisor()

    mapping = {
        "codex_cli": ("codex", ["--quiet"]),
        "claude_code": ("claude", ["--print"]),
        "opencode": ("opencode", ["--non-interactive"]),
        "agent_cli": ("codex", ["--quiet"]),
    }
    executable, base_args = mapping.get(adapter_type, ("codex", ["--quiet"]))
    prompt = spec.get("prompt", "")
    timeout = spec.get("timeout_seconds", 300)

    cmd = [executable, *base_args, prompt]
    info = await supervisor.start(run_id, cmd, timeout=timeout)
    result = await supervisor.wait(run_id, timeout=timeout)

    return {
        "exit_code": result.get("exit_code", -1),
        "stdout": result.get("stdout_preview", ""),
        "stderr": result.get("stderr_preview", ""),
    }


async def _execute_model(run_id: str, spec: dict) -> dict[str, Any]:
    """Execute an API Model run via ModelRuntime."""
    from ibreeze.runtime.model_loop import ModelRuntime
    from ibreeze.runtime.transport import create_transport

    binding = spec.get("model_binding", {})
    provider = binding.get("provider", "openai")
    model = binding.get("model", "gpt-4o")
    api_key = binding.get("api_key", "")

    transport = create_transport(provider, api_key=api_key, model=model)
    runtime = ModelRuntime(transport, tools={}, max_turns=50)

    result = await runtime.run(
        system_prompt=spec.get("system_prompt", "You are a helpful assistant."),
        user_message=spec.get("prompt", ""),
    )
    return {
        "exit_code": 0 if result.content else -1,
        "stdout": result.content,
        "stderr": "",
    }


async def _fail_run(
    db: Any, run_id: str, company_id: str, failure_code: str,
) -> None:
    """Mark a run as failed and write event."""
    now = _now()
    await db.execute(
        """UPDATE agent_runs
           SET status='failed', failure_code=?, completed_at=?,
               updated_at=?, version=version+1
           WHERE id=? AND company_id=?""",
        (failure_code, now, now, run_id, company_id),
    )
    await _write_event(db, company_id=company_id, run_id=run_id,
                       event_type="run_failed", payload={"failure_code": failure_code})
    await _feedback_to_tasks(db, run_id, company_id, False)


async def _feedback_to_tasks(
    db: Any, run_id: str, company_id: str, success: bool,
) -> None:
    """Propagate run completion back to employee_task → department_task → company_task."""
    now = _now()

    run_row = await (await db.execute(
        """SELECT employee_task_id, department_task_id, company_task_id
           FROM agent_runs WHERE id=? AND company_id=?""",
        (run_id, company_id),
    )).fetchone()
    if run_row is None:
        return
    run = dict(run_row)

    # Update employee_task
    if run.get("employee_task_id"):
        new_emp_status = "submitted" if success else "failed"
        await db.execute(
            """UPDATE employee_tasks
               SET status=?, updated_at=?, version=version+1
               WHERE id=? AND company_id=?""",
            (new_emp_status, now, run["employee_task_id"], company_id),
        )

    # Check if all employee_tasks for this department_task are done
    if run.get("department_task_id"):
        pending = await (await db.execute(
            """SELECT COUNT(*) as cnt FROM employee_tasks
               WHERE department_task_id=? AND company_id=?
               AND status NOT IN ('submitted','accepted','cancelled','failed')""",
            (run["department_task_id"], company_id),
        )).fetchone()
        if pending and pending["cnt"] == 0:
            any_failed = await (await db.execute(
                """SELECT COUNT(*) as cnt FROM employee_tasks
                   WHERE department_task_id=? AND company_id=? AND status='failed'""",
                (run["department_task_id"], company_id),
            )).fetchone()
            dept_status = "failed" if (any_failed and any_failed["cnt"] > 0) else "reviewing"
            await db.execute(
                """UPDATE department_tasks
                   SET status=?, updated_at=?, version=version+1
                   WHERE id=? AND company_id=?""",
                (dept_status, now, run["department_task_id"], company_id),
            )

            # Trigger downstream department_tasks
            downstream = await (await db.execute(
                """SELECT department_task_id FROM department_task_dependencies
                   WHERE depends_on_task_id=? AND company_task_id=?""",
                (run["department_task_id"], run["company_task_id"]),
            )).fetchall()
            for row in downstream:
                down_id = row["department_task_id"]
                unmet = await (await db.execute(
                    """SELECT COUNT(*) as cnt FROM department_task_dependencies d
                       JOIN department_tasks t ON t.id = d.depends_on_task_id
                       WHERE d.department_task_id=? AND t.status NOT IN ('completed','cancelled')""",
                    (down_id,),
                )).fetchone()
                if unmet and unmet["cnt"] == 0:
                    await db.execute(
                        """UPDATE department_tasks
                           SET status='ready', updated_at=?, version=version+1
                           WHERE id=? AND company_id=? AND status='waiting_dependency'""",
                        (now, down_id, company_id),
                    )

    # Check if all department_tasks for this company_task are done
    if run.get("company_task_id"):
        dept_pending = await (await db.execute(
            """SELECT COUNT(*) as cnt FROM department_tasks
               WHERE company_task_id=? AND company_id=?
               AND status NOT IN ('reviewing','completed','cancelled','failed')""",
            (run["company_task_id"], company_id),
        )).fetchone()
        if dept_pending and dept_pending["cnt"] == 0:
            any_dept_failed = await (await db.execute(
                """SELECT COUNT(*) as cnt FROM department_tasks
                   WHERE company_task_id=? AND company_id=? AND status='failed'""",
                (run["company_task_id"], company_id),
            )).fetchone()
            ct_status = "failed" if (any_dept_failed and any_dept_failed["cnt"] > 0) else "reviewing"
            await db.execute(
                """UPDATE company_tasks
                   SET status=?, updated_at=?, version=version+1
                   WHERE id=? AND company_id=? AND status='executing'""",
                (ct_status, now, run["company_task_id"], company_id),
            )

    await db.commit()


async def run_consumer_loop(
    db: Any,
    *,
    poll_interval: float = 1.0,
    max_concurrent: int = 4,
) -> None:
    """Main consumer loop: dequeue → lease → execute → complete."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _process_one() -> None:
        item = await dequeue_next(db)
        if item is None:
            return
        async with semaphore:
            lease_id = await acquire_lease(
                db,
                queue_id=item["id"],
                job_id=item["job_id"],
                run_id=item["run_id"],
                employee_id="",
                company_id=item["company_id"],
                conversation_id="",
            )
            if lease_id is None:
                return
            try:
                await execute_single_run(db, item["run_id"], item["company_id"])
            finally:
                await release_lease(db, lease_id)

    while True:
        try:
            await _process_one()
        except Exception:
            logger.exception("Consumer loop iteration failed")
        await asyncio.sleep(poll_interval)
