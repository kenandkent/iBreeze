"""Run executor — consumer loop that dequeues and executes agent runs.

Connects scheduler → CLI adapters / ModelRuntime → feedback to task states.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

from ibreeze.runtime.adapters.claude_code import ClaudeCodeAdapter
from ibreeze.runtime.adapters.codex import CodexAdapter
from ibreeze.runtime.adapters.opencode import OpenCodeAdapter
from ibreeze.runtime.process_supervisor import get_supervisor

logger = logging.getLogger("ibreeze.run_executor")

_TERMINAL_RUN = {"succeeded", "cancelled", "timed_out", "failed", "lost"}


@dataclass(frozen=True, slots=True)
class ClaimedRun:
    queue_id: str
    lease_id: str
    job_id: str
    run_id: str
    company_id: str
    employee_id: str
    conversation_id: str
    employee_task_id: str | None


class RuntimeExecutionService:
    """Execute leased runs without allowing a worker to write SQLite directly.

    The service deliberately splits each run into short WriteQueue transactions
    (claim, state transition, completion and lease release) and a process
    execution interval outside the transaction.  This keeps the single writer
    responsive while making every persisted transition atomic.
    """

    def __init__(
        self,
        read_pool: Any,
        write_queue: Any,
        command_bus: Any | None = None,
        *,
        max_concurrent: int = 4,
    ) -> None:
        self._read_pool = read_pool
        self._write_queue = write_queue
        self._command_bus = command_bus
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def work(self, heartbeat: Callable[[], None] | None = None) -> int:
        claimed = await self._claim_next()
        if claimed is None:
            return 0
        async with self._semaphore:
            await self._execute_claimed(claimed, heartbeat)
        return 1

    async def _claim_next(self) -> ClaimedRun | None:
        async def claim(conn: Any) -> ClaimedRun | None:
            cursor = await conn.execute(
                """SELECT q.id AS queue_id, q.job_id, q.run_id,
                          q.company_id, ar.employee_id, ar.conversation_id,
                          ar.employee_task_id
                   FROM runtime_queue q
                   JOIN agent_runs ar ON ar.id=q.run_id AND ar.company_id=q.company_id
                   LEFT JOIN runtime_company_fairness f ON f.company_id=q.company_id
                   WHERE q.status='ready' AND q.run_id IS NOT NULL
                   ORDER BY f.last_dispatched_at ASC NULLS FIRST,
                            q.priority ASC, q.queued_at ASC, q.id ASC
                   LIMIT 1"""
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            now = _now()
            updated = await conn.execute(
                """UPDATE runtime_queue
                   SET status='leased', leased_at=?
                   WHERE id=? AND status='ready'""",
                (now, row["queue_id"]),
            )
            if updated.rowcount != 1:
                return None
            lease_id = str(uuid4())
            await conn.execute(
                """INSERT INTO runtime_leases
                   (id, queue_id, job_id, run_id, employee_id, company_id,
                    conversation_id, acquired_at, heartbeat_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime(?, '+300 seconds'))""",
                (
                    lease_id,
                    row["queue_id"],
                    row["job_id"],
                    row["run_id"],
                    row["employee_id"],
                    row["company_id"],
                    row["conversation_id"],
                    now,
                    now,
                    now,
                ),
            )
            await conn.execute(
                """INSERT INTO runtime_company_fairness(company_id, last_dispatched_at)
                   VALUES (?, ?)
                   ON CONFLICT(company_id) DO UPDATE SET
                     last_dispatched_at=excluded.last_dispatched_at""",
                (row["company_id"], now),
            )
            return ClaimedRun(
                queue_id=str(row["queue_id"]),
                lease_id=lease_id,
                job_id=str(row["job_id"]),
                run_id=str(row["run_id"]),
                company_id=str(row["company_id"]),
                employee_id=str(row["employee_id"]),
                conversation_id=str(row["conversation_id"]),
                employee_task_id=(str(row["employee_task_id"]) if row["employee_task_id"] else None),
            )

        result = await self._write_queue.submit(
            "runtime.claim_next", uuid4(), _deadline(25), claim
        )
        return cast(ClaimedRun | None, result)

    async def _execute_claimed(
        self,
        claimed: ClaimedRun,
        heartbeat: Callable[[], None] | None,
    ) -> None:
        lease_heartbeat = asyncio.create_task(self._lease_heartbeat(claimed.lease_id, heartbeat))
        try:
            run = await self._read_pool.query_one(
                """SELECT id, company_id, adapter_type, run_spec_json,
                          employee_id, execution_snapshot_id, status, version
                   FROM agent_runs WHERE id=? AND company_id=?""",
                (claimed.run_id, claimed.company_id),
            )
            if run is None:
                return
            if run["status"] in _TERMINAL_RUN:
                return
            spec = json.loads(run["run_spec_json"])
            adapter_type = str(run["adapter_type"])
            run_version = int(run["version"])

            if not await _probe_adapter(adapter_type):
                await self._fail_claimed(claimed, "ADAPTER_UNAVAILABLE")
                return

            if run["status"] == "queued":
                if not await self._transition(
                    claimed, "queued", "probing", run_version, {"adapter_type": adapter_type}
                ):
                    return
                run_version += 1
                if not await self._transition(claimed, "probing", "starting", run_version, {}):
                    return
                run_version += 1
                if not await self._transition(
                    claimed,
                    "starting",
                    "running",
                    run_version,
                    {"started_at": _now()},
                ):
                    return
                run_version += 1
            elif run["status"] != "running":
                return

            snapshot = await self._load_snapshot(
                claimed.company_id,
                str(run["execution_snapshot_id"]),
            )
            if adapter_type in {"agent_cli", "codex_cli", "claude_code", "opencode"}:
                result = await _execute_cli(
                    claimed.run_id,
                    spec,
                    adapter_type,
                    company_id=claimed.company_id,
                    snapshot_data=snapshot,
                )
            elif adapter_type == "api_model":
                result = await _execute_model(
                    claimed.run_id,
                    spec,
                    snapshot_data=snapshot,
                )
            else:
                await self._fail_claimed(claimed, "UNKNOWN_ADAPTER_TYPE")
                return
            await self._complete_claimed(claimed, run_version, result)
        except asyncio.CancelledError:
            try:
                await get_supervisor().kill(claimed.run_id, reason="runtime worker stopped")
            except Exception:
                logger.exception("failed to cancel Rust process for run %s", claimed.run_id)
            raise
        except Exception as exc:
            from ibreeze.runtime.transport import ModelRunCancelledError

            if isinstance(exc, ModelRunCancelledError):
                # The control service has already committed run.cancelled;
                # never turn an intentional cancellation into run.failed.
                logger.info("API Model run %s cancelled", claimed.run_id)
                return
            logger.exception("run %s failed in RuntimeWorker", claimed.run_id)
            await self._fail_claimed(claimed, "EXECUTION_ERROR")
        finally:
            lease_heartbeat.cancel()
            await asyncio.gather(lease_heartbeat, return_exceptions=True)
            await self._release_claimed(claimed)

    async def _load_snapshot(self, company_id: str, snapshot_id: str) -> dict[str, Any]:
        row = await self._read_pool.query_one(
            """SELECT es.content_sha256, es.runtime_binding_json,
                      es.workspace_policy_json, tw.repository_root,
                      tw.workspace_grant_id,
                      bpv.system_prompt, bpv.tool_policy_json
               FROM execution_snapshots es
               LEFT JOIN task_workspaces tw
                 ON tw.id=es.task_workspace_id AND tw.company_id=es.company_id
               LEFT JOIN employee_base_profile_versions bpv
                 ON bpv.id=es.base_profile_version_id
               WHERE es.id=? AND es.company_id=?""",
            (snapshot_id, company_id),
        )
        if row is None:
            raise ValueError("EXECUTION_SNAPSHOT_NOT_FOUND")
        try:
            binding = json.loads(row["runtime_binding_json"] or "{}")
        except (TypeError, ValueError) as exc:
            raise ValueError("EXECUTION_SNAPSHOT_BINDING_INVALID") from exc
        return {
            "content_sha256": row["content_sha256"],
            "runtime_binding": binding,
            "workspace_policy_json": row["workspace_policy_json"],
            "repository_root": row["repository_root"],
            "workspace_grant_id": row["workspace_grant_id"],
            "system_prompt": row["system_prompt"] or "",
            "tool_policy_json": row["tool_policy_json"] or "{}",
        }

    async def _transition(
        self,
        claimed: ClaimedRun,
        from_state: str,
        to_state: str,
        expected_version: int,
        extra: dict[str, Any],
    ) -> bool:
        async def transition(conn: Any) -> bool:
            now = _now()
            assignments = ["status=?", "updated_at=?", "version=version+1"]
            params: list[Any] = [to_state, now]
            if "started_at" in extra:
                assignments.append("started_at=COALESCE(started_at, ?)")
                params.append(extra["started_at"])
            params.extend([claimed.run_id, claimed.company_id, from_state, expected_version])
            if to_state == "running" and claimed.employee_task_id:
                if self._command_bus is None:
                    raise RuntimeError("INTERNAL_COMMAND_BUS_UNAVAILABLE")
                task_cursor = await conn.execute(
                    "SELECT version FROM employee_tasks WHERE id=? AND company_id=?",
                    (claimed.employee_task_id, claimed.company_id),
                )
                task_row = await task_cursor.fetchone()
                if task_row is None:
                    raise ValueError("EMPLOYEE_TASK_NOT_FOUND")
                await self._command_bus.dispatch(
                    "StartEmployeeTask",
                    {
                        "company_id": claimed.company_id,
                        "task_id": claimed.employee_task_id,
                        "expected_version": int(task_row["version"]),
                    },
                    connection=conn,
                )
            cursor = await conn.execute(
                f"""UPDATE agent_runs SET {', '.join(assignments)}
                    WHERE id=? AND company_id=? AND status=? AND version=?""",
                tuple(params),
            )
            if cursor.rowcount != 1:
                return False
            event_type = "run.started" if to_state == "running" else f"run.{to_state}"
            await _write_event(
                conn,
                company_id=claimed.company_id,
                run_id=claimed.run_id,
                event_type=event_type,
                payload={
                    "company_id": claimed.company_id,
                    "aggregate_id": claimed.run_id,
                    "version": expected_version + 1,
                    "from_state": from_state,
                    "to_state": to_state,
                    **extra,
                },
            )
            return True

        result = await self._write_queue.submit(
            f"runtime.run.{to_state}", uuid4(), _deadline(30), transition
        )
        return bool(result)

    async def _complete_claimed(self, claimed: ClaimedRun, expected_version: int, result: dict[str, Any]) -> None:
        async def complete(conn: Any) -> None:
            process_status = str(result.get("status", ""))
            timed_out = bool(result.get("timed_out", False)) or process_status == "timed_out"
            cancelled = process_status == "cancelled"
            success = result.get("exit_code", -1) == 0 and not timed_out and not cancelled
            final_status = "timed_out" if timed_out else "cancelled" if cancelled else "succeeded" if success else "failed"
            now = _now()
            cursor = await conn.execute(
                """UPDATE agent_runs
                   SET status=?, completed_at=?, exit_code=?, failure_code=?,
                       updated_at=?, version=version+1
                   WHERE id=? AND company_id=? AND status='running' AND version=?""",
                (
                    final_status,
                    now,
                    result.get("exit_code", -1),
                    None if success else "RUN_TIMED_OUT" if timed_out else "RUN_CANCELLED" if cancelled else "AGENT_FAILED",
                    now,
                    claimed.run_id,
                    claimed.company_id,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                return
            # The public event registry has no separate timeout topic; a
            # timed-out run is terminal state ``timed_out`` carried by the
            # stable ``run.failed`` event and its failure code.
            event_type = "run.completed" if success else "run.cancelled" if cancelled else "run.failed"
            await _write_event(
                conn,
                company_id=claimed.company_id,
                run_id=claimed.run_id,
                event_type=event_type,
                payload={
                    "company_id": claimed.company_id,
                    "aggregate_id": claimed.run_id,
                    "version": expected_version + 1,
                    "from_state": "running",
                    "to_state": final_status,
                    "status": final_status,
                    "evidence_artifact_ids": [],
                    "exit_code": result.get("exit_code", -1),
                    "failure_code": None if success else "RUN_TIMED_OUT" if timed_out else "RUN_CANCELLED" if cancelled else "AGENT_FAILED",
                },
            )

        await self._write_queue.submit(
            "runtime.run.complete", uuid4(), _deadline(30), complete
        )

    async def _fail_claimed(self, claimed: ClaimedRun, failure_code: str) -> None:
        async def fail(conn: Any) -> None:
            now = _now()
            row = await (
                await conn.execute(
                    "SELECT status, version FROM agent_runs WHERE id=? AND company_id=?",
                    (claimed.run_id, claimed.company_id),
                )
            ).fetchone()
            if row is None or row["status"] in _TERMINAL_RUN:
                return
            from_state = str(row["status"])
            version = int(row["version"])
            cursor = await conn.execute(
                """UPDATE agent_runs
                   SET status='failed', failure_code=?, completed_at=?,
                       updated_at=?, version=version+1
                   WHERE id=? AND company_id=? AND status=? AND version=?""",
                (failure_code, now, now, claimed.run_id, claimed.company_id, from_state, version),
            )
            if cursor.rowcount != 1:
                return
            await _write_event(
                conn,
                company_id=claimed.company_id,
                run_id=claimed.run_id,
                event_type="run.failed",
                payload={
                    "company_id": claimed.company_id,
                    "aggregate_id": claimed.run_id,
                    "version": version + 1,
                    "from_state": from_state,
                    "to_state": "failed",
                    "failure_code": failure_code,
                },
            )

        await self._write_queue.submit(
            "runtime.run.fail", uuid4(), _deadline(30), fail
        )

    async def _release_claimed(self, claimed: ClaimedRun) -> None:
        async def release(conn: Any) -> None:
            await conn.execute(
                """UPDATE runtime_queue
                   SET status=CASE WHEN status='cancelled' THEN 'cancelled' ELSE 'completed' END
                   WHERE id=?""",
                (claimed.queue_id,),
            )
            await conn.execute("DELETE FROM runtime_leases WHERE id=?", (claimed.lease_id,))

        await self._write_queue.submit(
            "runtime.release_lease", uuid4(), _deadline(25), release
        )

    async def _lease_heartbeat(self, lease_id: str, heartbeat: Callable[[], None] | None) -> None:
        try:
            while True:
                await asyncio.sleep(30)
                if heartbeat:
                    heartbeat()

                async def refresh(conn: Any) -> None:
                    now = _now()
                    await conn.execute(
                        """UPDATE runtime_leases
                           SET heartbeat_at=?, expires_at=datetime(?, '+300 seconds')
                           WHERE id=? AND expires_at>?""",
                        (now, now, lease_id, now),
                    )

                await self._write_queue.submit(
                    "runtime.heartbeat_lease", uuid4(), _deadline(25), refresh
                )
        except asyncio.CancelledError:
            return


def _deadline(seconds: int) -> Any:
    from datetime import UTC, datetime, timedelta

    return datetime.now(UTC) + timedelta(seconds=seconds)


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_json_sha256(raw: object, error_code: str) -> str:
    """Hash the persisted policy value using the same canonical JSON form.

    Execution snapshots store policy JSON as text.  Hashing ``str(raw)``
    would make semantically identical JSON (whitespace/key order) produce a
    different Rust policy hash, so the boundary must parse and re-encode it
    deterministically before sending the fixed process request.
    """
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(error_code) from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _write_event(
    db: Any,
    *,
    company_id: str,
    run_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    import uuid

    event_id = str(uuid.uuid4())
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    await db.execute(
        """INSERT INTO agent_run_events
           (event_id, run_id, event_type, payload_json, sequence, trace_id, occurred_at)
           VALUES (?,?,?,?, COALESCE(
               (SELECT MAX(sequence)+1 FROM agent_run_events WHERE run_id=?), 1
           ),?,?)""",
        (event_id, run_id, event_type, payload_json, run_id, str(uuid.uuid4()), _now()),
    )
    # Run lifecycle events are also durable domain events.  Only the
    # canonical fields enter the domain-event/outbox contract; diagnostic
    # fields remain in agent_run_events for the run timeline.
    if event_type in {"run.queued", "run.started", "run.failed", "run.cancelled", "run.completed"}:
        required = {"company_id", "aggregate_id", "version", "from_state", "to_state"}
        if not required.issubset(payload):
            raise ValueError("RUN_EVENT_INVALID")
        canonical_keys = (
            "company_id",
            "aggregate_id",
            "version",
            "from_state",
            "to_state",
        )
        canonical_payload = {key: payload[key] for key in canonical_keys}
        if event_type == "run.completed":
            required_completed = {"status", "evidence_artifact_ids"}
            if not required_completed.issubset(payload):
                raise ValueError("RUN_COMPLETED_EVENT_INVALID")
            canonical_payload.update(
                {
                    "status": payload["status"],
                    "evidence_artifact_ids": payload["evidence_artifact_ids"],
                }
            )
        canonical_payload_json = json.dumps(
            canonical_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        await db.execute(
            """INSERT INTO domain_events
               (event_id, company_id, aggregate_type, aggregate_id,
                aggregate_version, event_type, payload_json, trace_id, occurred_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                event_id,
                company_id,
                "agent_run",
                run_id,
                int(payload["version"]),
                event_type,
                canonical_payload_json,
                str(uuid.uuid4()),
                _now(),
            ),
        )
        await db.execute(
            """INSERT INTO outbox_events
               (id, domain_event_id, topic, payload_json, status, attempts,
                next_attempt_at, created_at)
               VALUES (?,?,?,?, 'pending', 0, ?, ?)""",
            (
                str(uuid.uuid4()),
                event_id,
                event_type,
                canonical_payload_json,
                _now(),
                _now(),
            ),
        )


async def _probe_adapter(adapter_type: str) -> bool:
    """Check local CLI availability without bypassing the Rust supervisor.

    A preflight check must not launch an unbound process: the real execution
    path requires signed execution/workspace/network snapshots and is owned by
    Rust.  Presence of the allow-listed executable is therefore the only
    check performed here; the supervisor performs the authoritative checks at
    run start.
    """
    import shutil

    executable = {
        "codex_cli": "codex",
        "claude_code": "claude",
        "opencode": "opencode",
        "agent_cli": "codex",
    }.get(adapter_type)
    if executable is None:
        return adapter_type == "api_model"
    return shutil.which(executable) is not None


async def _execute_cli(
    run_id: str,
    spec: dict[str, Any],
    adapter_type: str,
    *,
    db: Any | None = None,
    company_id: str | None = None,
    execution_snapshot_id: str | None = None,
    snapshot_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a CLI adapter run using the structured adapter classes."""
    import shutil
    from pathlib import Path

    supervisor = get_supervisor()

    adapter = _get_adapter(adapter_type)
    if adapter is None:
        return {"exit_code": -1, "stdout": "", "stderr": "UNKNOWN_ADAPTER_TYPE"}

    prompt = spec.get("prompt", "")
    timeout = spec.get("timeout_seconds", 300)

    snapshot_row = None
    snapshot_binding: dict[str, Any] = {}
    if snapshot_data is not None:
        snapshot_row = snapshot_data
        snapshot_binding = dict(snapshot_data.get("runtime_binding") or {})
    elif db is not None and execution_snapshot_id:
        if not company_id:
            raise ValueError("COMPANY_SCOPE_REQUIRED")
        snapshot_row = await (
            await db.execute(
                """SELECT es.content_sha256, es.catalog_release_id,
                          es.runtime_binding_json, es.workspace_policy_json,
                          tw.repository_root, tw.workspace_grant_id
                   FROM execution_snapshots es
                   LEFT JOIN task_workspaces tw
                     ON tw.id=es.task_workspace_id AND tw.company_id=es.company_id
                   WHERE es.id=? AND es.company_id=?""",
                (execution_snapshot_id, company_id),
            )
        ).fetchone()
        if snapshot_row is None:
            raise ValueError("EXECUTION_SNAPSHOT_NOT_FOUND")
        try:
            snapshot_binding = json.loads(snapshot_row["runtime_binding_json"] or "{}")
        except (TypeError, ValueError) as exc:
            raise ValueError("EXECUTION_SNAPSHOT_BINDING_INVALID") from exc
    snapshot_workspace = snapshot_row["repository_root"] if snapshot_row else None
    workspace_value = snapshot_workspace or spec.get("workspace")
    if snapshot_workspace and spec.get("workspace") and Path(str(spec["workspace"])).resolve() != Path(str(snapshot_workspace)).resolve():
        raise ValueError("WORKSPACE_SNAPSHOT_MISMATCH")
    if not isinstance(workspace_value, str) or not workspace_value.strip():
        raise ValueError("WORKSPACE_SNAPSHOT_REQUIRED")
    workspace = Path(workspace_value).resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("WORKSPACE_ACCESS_DENIED")
    profile_root_value = os.environ.get("IBREEZE_PROFILE_ROOT")
    if not profile_root_value:
        raise ValueError("PROFILE_RUNTIME_ROOT_INVALID")
    profile_root = Path(profile_root_value).resolve(strict=True)
    runtime_root = profile_root / "runtime-input" / run_id
    runtime_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(runtime_root, stat.S_IRWXU)
    prompt_file = runtime_root / "prompt"
    prompt_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        prompt_flags |= os.O_NOFOLLOW
    prompt_fd = os.open(prompt_file, prompt_flags, 0o600)
    with os.fdopen(prompt_fd, "w", encoding="utf-8") as prompt_stream:
        prompt_stream.write(prompt)
    os.chmod(prompt_file, stat.S_IRUSR | stat.S_IWUSR)

    try:
        cmd = adapter.build_invocation(spec, str(prompt_file))
        executable = shutil.which(cmd[0])
        if executable is None:
            raise ValueError("AGENT_EXECUTABLE_NOT_FOUND")
        cmd[0] = executable
        process_request = _snapshot_process_fields(spec)
        if snapshot_row is not None:
            process_request.update(
                {
                    "execution_snapshot_sha256": snapshot_row["content_sha256"],
                    "agent_type": snapshot_binding.get("agent_type") or process_request.get("agent_type"),
                    "agent_release_id": snapshot_binding.get("agent_release_id")
                    or process_request.get("agent_release_id"),
                    "agent_key": snapshot_binding.get("agent_key") or snapshot_binding.get("agent_cli"),
                    "purpose": snapshot_binding.get("purpose") or process_request.get("purpose"),
                    "workspace_grant_id": snapshot_row["workspace_grant_id"],
                    "workspace_policy_sha256": _canonical_json_sha256(
                        snapshot_row["workspace_policy_json"],
                        "EXECUTION_WORKSPACE_POLICY_INVALID",
                    ),
                }
            )
        if not process_request.get("agent_type"):
            raise ValueError("AGENT_RUNTIME_BINDING_REQUIRED")
        await supervisor.start(
            run_id,
            cmd,
            cwd=str(workspace),
            timeout=timeout,
            **process_request,
        )
        result = await supervisor.wait(run_id, timeout=timeout)
    finally:
        try:
            prompt_file.unlink(missing_ok=True)
            try:
                runtime_root.rmdir()
            except OSError:
                pass
        except OSError:
            pass

    return {
        "exit_code": result.get("exit_code", -1),
        "stdout": result.get("stdout", result.get("stdout_preview", "")),
        "stderr": result.get("stderr", result.get("stderr_preview", "")),
        "status": result.get("status", "exited"),
        "timed_out": bool(result.get("timed_out", False)),
    }


def _snapshot_process_fields(spec: dict[str, Any]) -> dict[str, Any]:
    """Map persisted Run fields to the fixed Rust process contract."""
    return {
        "workspace_grant_id": spec.get("workspace_grant_id"),
        "agent_type": spec.get("agent_type")
        or {
            "codex_cli": "codex_cli",
            "claude_code": "claude_code",
            "opencode": "opencode",
            "agent_cli": "codex_cli",
        }.get(str(spec.get("adapter_type", ""))),
        "agent_release_id": spec.get("agent_release_id"),
        "agent_key": spec.get("agent_key"),
        "purpose": spec.get("purpose") or spec.get("run_purpose", "task_execution"),
        "execution_snapshot_sha256": spec.get("execution_snapshot_sha256"),
        "workspace_policy_sha256": spec.get("workspace_policy_sha256"),
    }


def _get_adapter(adapter_type: str) -> CodexAdapter | ClaudeCodeAdapter | OpenCodeAdapter | None:
    mapping = {
        "codex_cli": CodexAdapter,
        "claude_code": ClaudeCodeAdapter,
        "opencode": OpenCodeAdapter,
        "agent_cli": CodexAdapter,
    }
    cls = mapping.get(adapter_type)
    if cls is None:
        return None
    return cls()  # type: ignore[return-value]


async def _execute_model(
    run_id: str,
    spec: dict[str, Any],
    *,
    snapshot_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute an API Model run via ModelRuntime.

    Uses credential_ref instead of api_key - the Rust side
    resolves the credential_ref into actual credentials.
    """
    from pathlib import Path

    from ibreeze.runtime.model_loop import ModelRuntime
    from ibreeze.runtime.model_tools import ModelToolContext, build_model_tools
    from ibreeze.runtime.transport import create_transport, get_reverse_rpc_session

    has_snapshot = snapshot_data is not None
    binding = dict((snapshot_data or {}).get("runtime_binding") or {})
    # The execution snapshot is immutable and is the authority for model,
    # provider and credential binding.  The persisted Run spec may carry the
    # same values for display/replay, but it cannot switch a provider after
    # the snapshot has been created.
    credential_ref = (binding.get("credential_ref") if has_snapshot else None) or spec.get("credential_ref", "")
    model = (binding.get("api_model") if has_snapshot else None) or spec.get("model") or "gpt-4o"
    provider_release_id = (binding.get("provider_release_id") if has_snapshot else None) or spec.get("provider_release_id", "")
    model_binding_id = (binding.get("model_binding_id") if has_snapshot else None) or spec.get("model_binding_id", "")
    provider_protocol = (binding.get("provider_protocol") if has_snapshot else None) or spec.get("provider_protocol", "")
    binding_fields = (
        credential_ref,
        provider_release_id,
        model_binding_id,
        provider_protocol,
    )
    if not all(isinstance(value, str) and value.strip() for value in binding_fields):
        raise ValueError("API_MODEL_BINDING_REQUIRED")

    session = get_reverse_rpc_session()
    if session is None:
        raise ValueError("IPC_SESSION_REQUIRED")
    transport = create_transport(
        credential_ref=credential_ref,
        model=model,
        run_id=run_id,
        provider_release_id=provider_release_id,
        model_binding_id=model_binding_id,
        provider_protocol=provider_protocol,
        session=session,
    )
    snapshot_workspace = (snapshot_data or {}).get("repository_root")
    workspace_value = snapshot_workspace or spec.get("workspace")
    if snapshot_workspace and spec.get("workspace") and Path(str(spec["workspace"])).resolve() != Path(str(snapshot_workspace)).resolve():
        raise ValueError("MODEL_WORKSPACE_SNAPSHOT_MISMATCH")
    if not isinstance(workspace_value, str) or not workspace_value.strip():
        raise ValueError("MODEL_WORKSPACE_REQUIRED")
    workspace_root = Path(workspace_value).resolve(strict=True)
    if not workspace_root.is_dir():
        raise ValueError("MODEL_WORKSPACE_REQUIRED")
    tools = build_model_tools(
        ModelToolContext(
            workspace_root=workspace_root,
            purpose=str(spec.get("purpose") or spec.get("run_purpose") or "task_execution"),
        )
    )
    tool_policy_raw = (snapshot_data or {}).get("tool_policy_json", "{}")
    try:
        tool_policy = json.loads(tool_policy_raw) if isinstance(tool_policy_raw, str) else tool_policy_raw
    except (TypeError, ValueError) as exc:
        raise ValueError("MODEL_TOOL_POLICY_INVALID") from exc
    if isinstance(tool_policy, dict):
        allowed = tool_policy.get("allowed_tools", tool_policy.get("tools"))
        if allowed is not None:
            if not isinstance(allowed, list) or any(not isinstance(item, str) for item in allowed):
                raise ValueError("MODEL_TOOL_POLICY_INVALID")
            tools = {name: tool for name, tool in tools.items() if name in allowed}
    runtime = ModelRuntime(transport, tools=tools, max_turns=50)

    result = await runtime.run(
        system_prompt=(
            ((snapshot_data or {}).get("system_prompt") if has_snapshot else None)
            or spec.get("system_prompt")
            or "You are a helpful assistant."
        ),
        user_message=spec.get("prompt", ""),
    )
    return {
        "exit_code": 0 if result.content else -1,
        "stdout": result.content,
        "stderr": "",
    }


async def _fail_run(
    db: Any,
    run_id: str,
    company_id: str,
    failure_code: str,
) -> None:
    """Mark a run as failed and write event."""
    now = _now()
    cursor = await db.execute(
        """SELECT status, version FROM agent_runs
           WHERE id=? AND company_id=?""",
        (run_id, company_id),
    )
    row = await cursor.fetchone()
    if row is None or row["status"] in _TERMINAL_RUN:
        return
    from_state = row["status"]
    version = int(row["version"])
    updated = await db.execute(
        """UPDATE agent_runs
           SET status='failed', failure_code=?, completed_at=?,
               updated_at=?, version=version+1
           WHERE id=? AND company_id=? AND status=? AND version=?""",
        (failure_code, now, now, run_id, company_id, from_state, version),
    )
    if updated.rowcount != 1:
        return
    await _write_event(
        db,
        company_id=company_id,
        run_id=run_id,
        event_type="run.failed",
        payload={
            "company_id": company_id,
            "aggregate_id": run_id,
            "version": version + 1,
            "from_state": from_state,
            "to_state": "failed",
            "failure_code": failure_code,
        },
    )
