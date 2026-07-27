"""Adapter for Anthropic Claude Code CLI."""

from __future__ import annotations

import json
import shutil
from typing import Any


class ClaudeCodeAdapter:
    """Adapter for the Claude Code CLI agent.

    Builds invocations, parses output events, and manages
    checkpoint references for Claude Code CLI.
    """

    @staticmethod
    def probe() -> bool:
        """Check if the claude CLI is available on PATH."""
        return shutil.which("claude") is not None

    @staticmethod
    def build_invocation(spec: dict[str, Any], prompt_file: str) -> list[str]:
        """Build a Claude Code CLI command from a run spec and prompt file.

        Args:
            spec: Run specification dict (may contain model, permission_mode).
            prompt_file: Path to the file containing the prompt.

        Returns:
            Command list suitable for subprocess execution.
        """
        model = spec.get("model", "claude-sonnet-4-20250514")
        permission_mode = spec.get("permission_mode", "acceptEdits")
        cmd = [
            "claude",
            "--model", model,
            "--permission-mode", permission_mode,
            "--print",
            prompt_file,
        ]
        return cmd

    @staticmethod
    def parse_event(line: str) -> dict[str, Any] | None:
        """Parse a single line of Claude Code CLI output.

        Claude Code emits JSON event lines.

        Args:
            line: A line of stdout from Claude Code CLI.

        Returns:
            Parsed event dict, or None if the line is not a recognized event.
        """
        line = line.strip()
        if not line:
            return None
        try:
            return json.loads(line)  # type: ignore[no-any-return]
        except (json.JSONDecodeError, ValueError):
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
