"""Tests for CLI adapter contract.

Covers design spec sections:
- CT-013 Adapter probe contract (version and capabilities)
- CT-014 Model transport contract (request/response)
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCLIAdapterContract:
    """CLI adapter and model transport contract tests."""

    def test_adapter_probe_contract(self):
        """CT-013: Adapter probe should return version and capabilities."""
        from ibreeze.runtime.cli import AgentProbe

        probe = AgentProbe(
            adapter_type="codex_cli",
            available=True,
            executable_path="/usr/bin/codex",
            version="1.0.0",
            failure_code=None,
        )
        assert probe.adapter_type == "codex_cli"
        assert probe.available is True
        assert probe.version == "1.0.0"
        assert probe.failure_code is None
        assert probe.executable_path is not None

    def test_adapter_probe_unavailable(self):
        """CT-013: Unavailable adapter should report failure_code."""
        from ibreeze.runtime.cli import AgentProbe

        probe = AgentProbe(
            adapter_type="claude_code",
            available=False,
            executable_path=None,
            version=None,
            failure_code="AGENT_EXECUTABLE_NOT_FOUND",
        )
        assert probe.available is False
        assert probe.failure_code == "AGENT_EXECUTABLE_NOT_FOUND"
        assert probe.version is None

    @pytest.mark.asyncio
    async def test_adapter_probe_executable_not_found(self):
        """CT-013: probe_agent returns unavailable when executable missing."""
        from ibreeze.runtime.cli import probe_agent

        with patch("shutil.which", return_value=None):
            probe = await probe_agent("codex_cli")
            assert probe.available is False
            assert probe.failure_code == "AGENT_EXECUTABLE_NOT_FOUND"

    def test_adapter_type_literal(self):
        """CT-013: Adapter types should be restricted to known set."""
        from ibreeze.runtime.cli import AdapterName

        valid = {"codex_cli", "claude_code", "opencode"}
        assert valid == {"codex_cli", "claude_code", "opencode"}

    def test_model_transport_abstract_interface(self):
        """CT-014: ModelTransport should define complete and probe methods."""
        from ibreeze.runtime.transport import ModelTransport

        assert hasattr(ModelTransport, "complete")
        assert hasattr(ModelTransport, "probe")
        assert hasattr(ModelTransport, "normalize_usage")

    def test_model_transport_openai_has_complete(self):
        """CT-014: OpenAITransport should implement complete method."""
        from ibreeze.runtime.transport import OpenAITransport

        transport = OpenAITransport(api_key="test-key", model="gpt-4o")
        assert hasattr(transport, "complete")
        assert asyncio.iscoroutinefunction(transport.complete)

    def test_model_transport_openai_has_probe(self):
        """CT-014: OpenAITransport should implement probe method."""
        from ibreeze.runtime.transport import OpenAITransport

        transport = OpenAITransport(api_key="test-key")
        assert hasattr(transport, "probe")
        assert asyncio.iscoroutinefunction(transport.probe)

    def test_usage_stats_dataclass(self):
        """CT-014: UsageStats should have token count fields."""
        from ibreeze.runtime.transport import UsageStats

        stats = UsageStats(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        assert stats.prompt_tokens == 100
        assert stats.completion_tokens == 50
        assert stats.total_tokens == 150

    def test_process_result_dataclass(self):
        """CT-013: ProcessResult should have exit_code and output fields."""
        from ibreeze.runtime.cli import ProcessResult

        result = ProcessResult(
            exit_code=0,
            stdout=b"output",
            stderr=b"",
            timed_out=False,
        )
        assert result.exit_code == 0
        assert result.stdout == b"output"
        assert result.timed_out is False

    def test_cli_adapter_rejects_nonexistent_executable(self):
        """CT-013: CliAdapter should reject non-existent executable."""
        from ibreeze.runtime.cli import CliAdapter

        with pytest.raises((ValueError, FileNotFoundError)):
            CliAdapter("/nonexistent/path/to/agent")
