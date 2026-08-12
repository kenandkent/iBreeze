"""Sidecar facade for the Rust-owned Agent process supervisor.

The Sidecar builds the fixed execution request, but never starts a child
process itself.  Rust validates the executable/policy snapshot, owns the
process group and the per-run egress lease, and returns terminal output.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ibreeze.runtime.transport import ReverseRpcClient

_AGENT_NAMES = {
    "codex": "codex_cli",
    "claude": "claude_code",
    "opencode": "opencode",
}
_PURPOSES = {
    "task_execution",
    "review",
    "repair",
    "verification",
    "merge",
    "company_plan",
    "summary",
    "interactive_turn",
}
_MAX_OUTPUT_BYTES = 16 * 1024 * 1024
_MAX_LOGICAL_LINE_BYTES = 4 * 1024 * 1024


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _catalog_snapshot() -> dict[str, Any]:
    profile_root = os.environ.get("IBREEZE_PROFILE_ROOT")
    if not profile_root:
        raise ValueError("EXECUTION_NETWORK_POLICY_UNAVAILABLE")
    snapshot_path = Path(profile_root) / "catalog-snapshot.v1.json"
    try:
        snapshot = json.loads(snapshot_path.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("EXECUTION_NETWORK_POLICY_UNAVAILABLE") from exc
    if not isinstance(snapshot, dict):
        raise ValueError("EXECUTION_NETWORK_POLICY_INVALID")
    return snapshot


def _catalog_network_policy_hash() -> str:
    snapshot = _catalog_snapshot()
    domains: set[str] = set()
    for provider in snapshot.get("providers", []):
        if not isinstance(provider, dict):
            raise ValueError("EXECUTION_NETWORK_POLICY_INVALID")
        from urllib.parse import urlparse

        parsed = urlparse(str(provider.get("base_url", "")))
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("EXECUTION_NETWORK_POLICY_INVALID")
        domains.add(parsed.hostname.lower())
    for agent in snapshot.get("agents", []):
        if not isinstance(agent, dict):
            raise ValueError("EXECUTION_NETWORK_POLICY_INVALID")
        for domain in agent.get("network_domains", []):
            if not isinstance(domain, str) or not domain.strip():
                raise ValueError("EXECUTION_NETWORK_POLICY_INVALID")
            domains.add(domain.strip().lower())
    encoded = json.dumps(sorted(domains), separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _catalog_agent_release_id(agent_type: str, agent_key: str | None) -> str:
    snapshot = _catalog_snapshot()
    agents = snapshot.get("agents", [])
    if not isinstance(agents, list):
        raise ValueError("AGENT_RELEASE_NOT_REGISTERED")
    normalized_key = (agent_key or "").strip().lower()
    aliases = {agent_type.lower(), agent_type.removesuffix("_cli").lower()}
    for item in agents:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip().lower()
        release_id = str(item.get("agent_release_id", "")).strip()
        if key and (key == normalized_key or (not normalized_key and key in aliases)):
            try:
                uuid.UUID(release_id)
            except ValueError as exc:
                raise ValueError("AGENT_RELEASE_INVALID") from exc
            return release_id
    raise ValueError("AGENT_RELEASE_NOT_REGISTERED")


class ProcessSupervisor:
    def __init__(self, rpc: ReverseRpcClient | None = None) -> None:
        self._rpc = rpc or ReverseRpcClient()
        self._process_ids: dict[str, str] = {}
        self._notification_outputs: dict[str, dict[str, Any]] = {}

    async def start(
        self,
        run_id: str,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 600,
        stdin: bytes = b"",
        workspace_grant_id: str | None = None,
        agent_type: str | None = None,
        agent_key: str | None = None,
        agent_release_id: str | None = None,
        purpose: str = "task_execution",
        execution_snapshot_sha256: str | None = None,
        workspace_policy_sha256: str | None = None,
        network_policy_sha256: str | None = None,
    ) -> dict[str, Any]:
        del env  # Arbitrary environment injection is intentionally forbidden.
        if not cmd or any(not isinstance(part, str) or not part for part in cmd):
            raise ValueError("PROCESS_ARGV_INVALID")
        if purpose not in _PURPOSES:
            raise ValueError("PROCESS_PURPOSE_INVALID")
        workspace = Path(cwd or ".").resolve(strict=True)
        if not workspace.is_dir():
            raise ValueError("WORKSPACE_ACCESS_DENIED")
        executable = Path(cmd[0]).resolve(strict=True)
        if not executable.is_file():
            raise ValueError("AGENT_EXECUTABLE_NOT_FOUND")
        cmd = [str(executable), *cmd[1:]]
        resolved_agent_type = agent_type or _AGENT_NAMES.get(executable.name)
        if resolved_agent_type is None:
            raise ValueError("AGENT_TYPE_UNSUPPORTED")
        if resolved_agent_type not in {"codex_cli", "claude_code", "opencode"}:
            raise ValueError("AGENT_TYPE_UNSUPPORTED")
        if timeout <= 0:
            raise ValueError("PROCESS_DEADLINE_INVALID")
        try:
            run_uuid = uuid.UUID(run_id)
        except ValueError as exc:
            raise ValueError("RUN_ID_INVALID") from exc
        try:
            workspace_grant_uuid = uuid.UUID(str(workspace_grant_id))
        except (ValueError, TypeError) as exc:
            raise ValueError("WORKSPACE_GRANT_REQUIRED") from exc
        if not agent_release_id:
            agent_release_id = _catalog_agent_release_id(resolved_agent_type, agent_key)
        release_uuid = uuid.UUID(agent_release_id)
        locale = os.environ.get("LC_ALL") or os.environ.get("LANG") or "en_US.UTF-8"
        request_snapshot = {
            "run_id": run_id,
            "workspace_grant_id": str(workspace_grant_uuid),
            "agent_release_id": str(release_uuid),
            "agent_type": resolved_agent_type,
            "executable_realpath": str(executable),
            "argv": cmd,
            "cwd_realpath": str(workspace),
            "purpose": purpose,
        }
        if network_policy_sha256 is None:
            network_policy_sha256 = _catalog_network_policy_hash()
        required_hashes = {
            "execution_snapshot_sha256": execution_snapshot_sha256,
            "workspace_policy_sha256": workspace_policy_sha256,
            "network_policy_sha256": network_policy_sha256,
        }
        for value in required_hashes.values():
            if not isinstance(value, str) or len(value) != 64:
                raise ValueError("PROCESS_SNAPSHOT_REQUIRED")
            if any(ch not in "0123456789abcdef" for ch in value):
                raise ValueError("PROCESS_SNAPSHOT_HASH_INVALID")
        request = {
            **request_snapshot,
            "execution_snapshot_sha256": execution_snapshot_sha256,
            "stdin_base64": base64.b64encode(stdin).decode("ascii") if stdin else None,
            "locale": locale,
            "workspace_policy_sha256": workspace_policy_sha256,
            "network_policy_sha256": network_policy_sha256,
            "deadline_at": (
                datetime.now(UTC) + timedelta(seconds=timeout)
            ).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        }
        # Keep UUID construction in this facade explicit: the Rust boundary
        # rejects malformed IDs before any process or lease is created.
        request["run_id"] = str(run_uuid)
        response = await self._rpc.call("runtime.process.start", request)
        process_id = str(response.get("process_id", run_id))
        self._process_ids[run_id] = process_id
        return response

    def _process_id(self, run_id: str) -> str:
        return self._process_ids.get(run_id, run_id)

    async def handle_notification(self, method: str, payload: dict[str, Any]) -> None:
        """Merge Rust process notifications idempotently.

        Status remains the recovery source of truth; these notifications are
        used for live output and to correlate a process ID before the start
        response is consumed by a caller.
        """
        if method == "runtime.process.registered":
            process_id = str(payload.get("process_id", ""))
            run_id = str(payload.get("run_id", ""))
            if not process_id or not run_id:
                raise ValueError("RUNTIME_PROCESS_NOTIFICATION_INVALID")
            self._process_ids[run_id] = process_id
            self._notification_outputs.setdefault(
                run_id,
                {
                    "process_id": process_id,
                    "stdout": bytearray(),
                    "stderr": bytearray(),
                    "last_sequence": 0,
                    "last_event": None,
                    "line_bytes": {"stdout": 0, "stderr": 0},
                },
            )
            return
        if method == "runtime.process.output":
            process_id = str(payload.get("process_id", ""))
            run_id = str(payload.get("run_id", ""))
            stream = payload.get("stream")
            sequence = payload.get("sequence")
            encoded = payload.get("chunk_base64")
            if (
                not process_id
                or not run_id
                or stream not in {"stdout", "stderr"}
                or not isinstance(sequence, int)
                or sequence < 1
                or not isinstance(encoded, str)
            ):
                raise ValueError("RUNTIME_PROCESS_OUTPUT_INVALID")
            try:
                chunk = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError("RUNTIME_PROCESS_OUTPUT_INVALID") from exc
            if len(chunk) > 256 * 1024:
                raise ValueError("RUNTIME_OUTPUT_CHUNK_TOO_LARGE")
            output = self._notification_outputs.setdefault(
                run_id,
                {
                    "process_id": process_id,
                    "stdout": bytearray(),
                    "stderr": bytearray(),
                    "last_sequence": 0,
                    "last_event": None,
                    "line_bytes": {"stdout": 0, "stderr": 0},
                },
            )
            if output.get("process_id") != process_id:
                raise ValueError("RUNTIME_PROCESS_CORRELATION_INVALID")
            last_sequence = output["last_sequence"]
            if sequence <= last_sequence:
                event = output.get("last_event")
                if event == (stream, sequence, encoded):
                    return
                raise ValueError("RUNTIME_PROCESS_OUTPUT_DUPLICATE")
            if sequence != last_sequence + 1:
                raise ValueError("RUNTIME_PROCESS_OUTPUT_SEQUENCE_INVALID")
            line_bytes = output.setdefault("line_bytes", {"stdout": 0, "stderr": 0})
            current_line = int(line_bytes.get(stream, 0))
            parts = chunk.split(b"\n")
            if len(parts) == 1:
                next_line = current_line + len(parts[0])
                if next_line > _MAX_LOGICAL_LINE_BYTES:
                    raise ValueError("RUNTIME_OUTPUT_LIMIT_EXCEEDED")
            else:
                if current_line + len(parts[0]) > _MAX_LOGICAL_LINE_BYTES:
                    raise ValueError("RUNTIME_OUTPUT_LIMIT_EXCEEDED")
                if any(len(part) > _MAX_LOGICAL_LINE_BYTES for part in parts[1:-1]):
                    raise ValueError("RUNTIME_OUTPUT_LIMIT_EXCEEDED")
                next_line = len(parts[-1])
                if next_line > _MAX_LOGICAL_LINE_BYTES:
                    raise ValueError("RUNTIME_OUTPUT_LIMIT_EXCEEDED")
            if len(output[stream]) + len(chunk) > _MAX_OUTPUT_BYTES:
                raise ValueError("RUNTIME_OUTPUT_LIMIT_EXCEEDED")
            output[stream].extend(chunk)
            line_bytes[stream] = next_line
            output["last_sequence"] = sequence
            output["last_event"] = (stream, sequence, encoded)
            return
        if method == "runtime.process.exited":
            process_id = str(payload.get("process_id", ""))
            run_id = str(payload.get("run_id", ""))
            last_sequence = payload.get("last_sequence")
            if not process_id or not run_id or not isinstance(last_sequence, int) or last_sequence < 0:
                raise ValueError("RUNTIME_PROCESS_EXITED_INVALID")
            output = self._notification_outputs.setdefault(
                run_id,
                {
                    "process_id": process_id,
                    "stdout": bytearray(),
                    "stderr": bytearray(),
                    "last_sequence": 0,
                    "last_event": None,
                },
            )
            if output.get("process_id") != process_id or last_sequence != output["last_sequence"]:
                raise ValueError("RUNTIME_PROCESS_EXIT_SEQUENCE_INVALID")
            output["terminal"] = dict(payload)
            return
        if method == "credential.http.event":
            if not isinstance(payload, dict) or not payload.get("run_id"):
                raise ValueError("CREDENTIAL_HTTP_EVENT_INVALID")
            return
        raise ValueError("RUNTIME_PROCESS_NOTIFICATION_UNKNOWN")

    async def wait(self, run_id: str, timeout: int = 600) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + timeout
        process_id = self._process_id(run_id)
        while True:
            result = await self._rpc.call(
                "runtime.process.status", {"process_id": process_id, "run_id": run_id}
            )
            if result.get("state") not in {"running"} and result.get("status") not in {
                "running",
                "cancellation_requested",
            }:
                return result
            if asyncio.get_running_loop().time() >= deadline:
                result = await self.kill(run_id, reason="sidecar wait timeout")
                if result.get("state") == "exited":
                    return result
                return {"run_id": run_id, "exit_code": -1, "error": "timeout", "state": "exited"}
            await asyncio.sleep(0.1)

    async def kill(self, run_id: str, reason: str = "cancelled by sidecar") -> dict[str, Any]:
        return await self._rpc.call(
            "runtime.process.cancel",
            {"process_id": self._process_id(run_id), "run_id": run_id, "reason": reason},
        )

    async def heartbeat_check(self, run_id: str) -> bool:
        try:
            result = await self.status(run_id)
        except Exception:
            return False
        return result.get("state") == "running" or result.get("status") in {
            "running",
            "cancellation_requested",
        }

    async def status(self, run_id: str) -> dict[str, Any]:
        return await self._rpc.call(
            "runtime.process.status", {"process_id": self._process_id(run_id), "run_id": run_id}
        )


_supervisor: ProcessSupervisor | None = None


def get_supervisor() -> ProcessSupervisor:
    global _supervisor
    if _supervisor is None:
        _supervisor = ProcessSupervisor()
    return _supervisor
