"""Contract tests for CLI adapters (Codex, Claude Code, OpenCode).

Uses fake CLI scripts to simulate agent behavior and verifies
the adapter contract: probe, build_invocation, parse_event, checkpoint.
"""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any

import pytest

from ibreeze.runtime.adapters.claude_code import ClaudeCodeAdapter
from ibreeze.runtime.adapters.codex import CodexAdapter
from ibreeze.runtime.adapters.opencode import OpenCodeAdapter


@pytest.fixture
def fake_bin_dir() -> Any:
    """Create a temporary bin directory with fake CLI scripts."""
    tmpdir = tempfile.mkdtemp()
    orig_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{tmpdir}:{orig_path}"
    yield Path(tmpdir)
    os.environ["PATH"] = orig_path
    shutil.rmtree(tmpdir, ignore_errors=True)


def _make_fake_cli(bin_dir: Path, name: str, exit_code: int = 0, version: str = "1.0.0") -> Path:
    """Create a fake CLI script that prints version and exits cleanly."""
    script = bin_dir / name
    script.write_text(
        f"#!/bin/sh\n"
        f'if [ "$1" = "--version" ]; then\n'
        f'  echo "{name} version {version}"\n'
        f"  exit {exit_code}\n"
        f"fi\n"
        f'echo "fake {name} executed"\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


class TestCodexAdapter:
    def test_probe_found(self, fake_bin_dir: Path) -> None:
        _make_fake_cli(fake_bin_dir, "codex")
        assert CodexAdapter.probe() is True

    def test_probe_not_found(self) -> None:
        # Ensure codex is not on PATH
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("PATH", "")
            os.environ["PATH"] = tmp
            try:
                assert CodexAdapter.probe() is False
            finally:
                os.environ["PATH"] = old

    def test_build_invocation_defaults(self) -> None:
        spec: dict[str, Any] = {}
        cmd = CodexAdapter.build_invocation(spec, "/tmp/prompt.md")
        assert cmd[0] == "codex"
        assert "--model" in cmd
        assert cmd[cmd.index("--model") + 1] == "codex-mini-latest"
        assert "--quiet" in cmd
        assert cmd[-1] == "/tmp/prompt.md"

    def test_build_invocation_with_model(self) -> None:
        spec = {"model": "gpt-4o"}
        cmd = CodexAdapter.build_invocation(spec, "/tmp/p.md")
        assert cmd[cmd.index("--model") + 1] == "gpt-4o"

    def test_build_invocation_with_approval_mode(self) -> None:
        spec = {"approval_mode": "auto"}
        cmd = CodexAdapter.build_invocation(spec, "/tmp/p.md")
        idx = cmd.index("--approval-mode")
        assert cmd[idx + 1] == "auto"

    def test_parse_event_valid(self) -> None:
        event = CodexAdapter.parse_event('event: {"type":"text","content":"hello"}')
        assert event is not None
        assert event["type"] == "text"

    def test_parse_event_invalid(self) -> None:
        event = CodexAdapter.parse_event("event: not-json")
        assert event is None

    def test_parse_event_non_event_line(self) -> None:
        event = CodexAdapter.parse_event("just some output")
        assert event is None

    def test_checkpoint_returns_hash(self) -> None:
        ref = CodexAdapter.checkpoint({"step": 1})
        assert isinstance(ref, str)
        assert len(ref) == 32

    def test_checkpoint_deterministic(self) -> None:
        ref1 = CodexAdapter.checkpoint({"a": 1, "b": 2})
        ref2 = CodexAdapter.checkpoint({"a": 1, "b": 2})
        assert ref1 == ref2


class TestClaudeCodeAdapter:
    def test_probe_found(self, fake_bin_dir: Path) -> None:
        _make_fake_cli(fake_bin_dir, "claude")
        assert ClaudeCodeAdapter.probe() is True

    def test_probe_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("PATH", "")
            os.environ["PATH"] = tmp
            try:
                assert ClaudeCodeAdapter.probe() is False
            finally:
                os.environ["PATH"] = old

    def test_build_invocation_defaults(self) -> None:
        spec: dict[str, Any] = {}
        cmd = ClaudeCodeAdapter.build_invocation(spec, "/tmp/prompt.md")
        assert cmd[0] == "claude"
        assert "--model" in cmd
        assert cmd[cmd.index("--model") + 1] == "claude-sonnet-4-20250514"
        assert "--print" in cmd
        assert cmd[-1] == "/tmp/prompt.md"

    def test_build_invocation_with_permission_mode(self) -> None:
        spec = {"permission_mode": "bypass"}
        cmd = ClaudeCodeAdapter.build_invocation(spec, "/tmp/p.md")
        idx = cmd.index("--permission-mode")
        assert cmd[idx + 1] == "bypass"

    def test_parse_event_valid_json(self) -> None:
        event = ClaudeCodeAdapter.parse_event('{"type":"text","content":"hello"}')
        assert event is not None
        assert event["type"] == "text"

    def test_parse_event_empty_line(self) -> None:
        assert ClaudeCodeAdapter.parse_event("") is None

    def test_parse_event_invalid(self) -> None:
        assert ClaudeCodeAdapter.parse_event("not json") is None

    def test_checkpoint(self) -> None:
        ref = ClaudeCodeAdapter.checkpoint({"step": 1})
        assert isinstance(ref, str)
        assert len(ref) == 32


class TestOpenCodeAdapter:
    def test_probe_found(self, fake_bin_dir: Path) -> None:
        _make_fake_cli(fake_bin_dir, "opencode")
        assert OpenCodeAdapter.probe() is True

    def test_probe_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("PATH", "")
            os.environ["PATH"] = tmp
            try:
                assert OpenCodeAdapter.probe() is False
            finally:
                os.environ["PATH"] = old

    def test_build_invocation_defaults(self) -> None:
        spec: dict[str, Any] = {}
        cmd = OpenCodeAdapter.build_invocation(spec, "/tmp/prompt.md")
        assert cmd[0] == "opencode"
        assert "--model" in cmd
        assert cmd[cmd.index("--model") + 1] == "anthropic/claude-sonnet-4-20250514"
        assert "--non-interactive" in cmd
        assert cmd[-1] == "/tmp/prompt.md"

    def test_build_invocation_with_model(self) -> None:
        spec = {"model": "gpt-4o"}
        cmd = OpenCodeAdapter.build_invocation(spec, "/tmp/p.md")
        assert cmd[cmd.index("--model") + 1] == "gpt-4o"

    def test_parse_event_valid(self) -> None:
        event = OpenCodeAdapter.parse_event('{"type":"tool","name":"bash"}')
        assert event is not None
        assert event["name"] == "bash"

    def test_parse_event_empty(self) -> None:
        assert OpenCodeAdapter.parse_event("") is None

    def test_checkpoint(self) -> None:
        ref = OpenCodeAdapter.checkpoint({"step": 1})
        assert isinstance(ref, str)
        assert len(ref) == 32
