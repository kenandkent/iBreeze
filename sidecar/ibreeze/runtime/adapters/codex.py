"""Adapter for OpenAI Codex CLI."""

from __future__ import annotations

import json
import shutil
from typing import Any


class CodexAdapter:
    """Adapter for the Codex CLI agent.

    Builds invocations, parses output events, and manages
    checkpoint references for Codex CLI.
    """

    @staticmethod
    def probe() -> bool:
        """Check if the codex CLI is available on PATH."""
        return shutil.which("codex") is not None

    @staticmethod
    def build_invocation(spec: dict[str, Any], prompt_file: str) -> list[str]:
        """Build a Codex CLI command from a run spec and prompt file.

        Args:
            spec: Run specification dict (may contain model, approval_mode, timeout_seconds).
            prompt_file: Path to the file containing the prompt.

        Returns:
            Command list suitable for subprocess execution.
        """
        model = spec.get("model", "codex-mini-latest")
        approval_mode = spec.get("approval_mode", "suggest")
        cmd = [
            "codex",
            "--model", model,
            "--approval-mode", approval_mode,
            "--quiet",
            prompt_file,
        ]
        return cmd

    @staticmethod
    def parse_event(line: str) -> dict[str, Any] | None:
        """Parse a single line of Codex CLI output.

        Codex emits JSON event lines prefixed with ''event: ''.

        Args:
            line: A line of stdout from Codex CLI.

        Returns:
            Parsed event dict, or None if the line is not a recognized event.
        """
        if line.startswith("event: "):
            try:
                return json.loads(line[7:])  # type: ignore[no-any-return]
            except (json.JSONDecodeError, ValueError):
                return None
        return None

    @staticmethod
    def checkpoint(native_state: dict[str, Any]) -> str:
        """Persist a native checkpoint reference.

        Args:
            native_state: Opaque state dict from the CLI agent.

        Returns:
            Checkpoint ref string.
        """
        import hashlib
        raw = json.dumps(native_state, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
