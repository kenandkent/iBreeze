"""Process security: minimal environment and command sanitization."""

from __future__ import annotations

import os


def minimal_env() -> dict[str, str]:
    """Return minimal environment variables for CLI subprocess."""
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": "en_US.UTF-8",
        "TERM": "dumb",
    }


def sanitize_command_args(args: list[str]) -> list[str]:
    """Remove dangerous flags from command arguments."""
    forbidden = {"--dangerously-skip-permissions", "--max-budget-usd", "--share", "--attach"}
    return [a for a in args if a not in forbidden]
