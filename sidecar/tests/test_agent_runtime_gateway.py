"""Tests for Agent Runtime Gateway modules."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ibreeze.runtime.cli import (
    CliAdapter,
    CodexCliAdapter,
    ClaudeCodeAdapter,
    OpenCodeAdapter,
    AgentProbe,
    ProcessResult,
    create_adapter,
    probe_agent,
)
from ibreeze.runtime.model_loop import (
    AgentLoopResult,
    Checkpoint,
    ModelRuntime,
    ModelTurn,
    ToolCall,
    ToolPermission,
)
from ibreeze.runtime.transport import (
    AnthropicTransport,
    OpenAITransport,
    UsageStats,
    create_transport,
)
from ibreeze.events import (
    EventEnvelope,
    EventPublisher,
    EventType,
    serialize_event,
    deserialize_event,
)


class TestCliAdapter:
    """Tests for CLI adapters."""

    @pytest.mark.asyncio
    async def test_probe_agent_returns_probe(self):
        with patch("ibreeze.runtime.cli.shutil.which", return_value=None):
            result = await probe_agent("codex_cli")
            assert isinstance(result, AgentProbe)
            assert result.available is False
            assert result.failure_code == "AGENT_EXECUTABLE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_probe_agent_with_executable(self):
        with patch("ibreeze.runtime.cli.shutil.which", return_value="/usr/bin/codex"):
            with patch("ibreeze.runtime.cli.asyncio.create_subprocess_exec") as mock_proc:
                mock_process = AsyncMock()
                mock_process.communicate = AsyncMock(return_value=(b"1.0.0", b""))
                mock_process.returncode = 0
                mock_proc.return_value = mock_process

                result = await probe_agent("codex_cli")
                assert result.available is True
                assert result.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_probe_agent_timeout(self):
        with patch("ibreeze.runtime.cli.shutil.which", return_value="/usr/bin/codex"):
            with patch("ibreeze.runtime.cli.asyncio.create_subprocess_exec") as mock_proc:
                mock_process = AsyncMock()
                mock_process.communicate = AsyncMock(side_effect=TimeoutError)
                mock_process.kill = AsyncMock()
                mock_process.wait = AsyncMock()
                mock_proc.return_value = mock_process

                result = await probe_agent("codex_cli", timeout_seconds=0.1)
                assert result.available is False
                assert result.failure_code == "AGENT_PROBE_TIMED_OUT"

    def test_create_adapter_factory(self):
        with patch.object(CliAdapter, '__init__', return_value=None):
            with patch("ibreeze.runtime.cli.shutil.which", return_value="/usr/bin/codex"):
                adapter = create_adapter("codex_cli")
                assert isinstance(adapter, CodexCliAdapter)

    def test_codex_adapter_requires_executable(self):
        with patch.object(CliAdapter, '__init__', side_effect=ValueError("AGENT_EXECUTABLE_NOT_FOUND")):
            with pytest.raises(ValueError, match="AGENT_EXECUTABLE_NOT_FOUND"):
                CodexCliAdapter(executable="/nonexistent/path")

    def test_claude_adapter_requires_executable(self):
        with patch.object(CliAdapter, '__init__', side_effect=ValueError("AGENT_EXECUTABLE_NOT_FOUND")):
            with pytest.raises(ValueError, match="AGENT_EXECUTABLE_NOT_FOUND"):
                ClaudeCodeAdapter(executable="/nonexistent/path")

    def test_opencode_adapter_requires_executable(self):
        with patch.object(CliAdapter, '__init__', side_effect=ValueError("AGENT_EXECUTABLE_NOT_FOUND")):
            with pytest.raises(ValueError, match="AGENT_EXECUTABLE_NOT_FOUND"):
                OpenCodeAdapter(executable="/nonexistent/path")


class TestModelRuntime:
    """Tests for ModelRuntime."""

    @pytest.mark.asyncio
    async def test_model_runtime_completes_without_tools(self):
        mock_transport = AsyncMock()
        mock_transport.complete = AsyncMock(return_value=ModelTurn(content="Hello"))

        runtime = ModelRuntime(mock_transport, {})
        result = await runtime.run(
            system_prompt="test",
            user_message="hello",
        )
        assert isinstance(result, AgentLoopResult)
        assert result.content == "Hello"
        assert result.turns == 1
        assert result.tool_executions == 0

    @pytest.mark.asyncio
    async def test_model_runtime_with_tool_calls(self):
        mock_transport = AsyncMock()
        mock_transport.complete = AsyncMock(side_effect=[
            ModelTurn(content="", tool_calls=(
                ToolCall(id="1", name="test_tool", arguments={"x": 1}),
            )),
            ModelTurn(content="Done"),
        ])

        async def test_tool(args):
            return "result"

        runtime = ModelRuntime(mock_transport, {"test_tool": test_tool})
        result = await runtime.run(
            system_prompt="test",
            user_message="hello",
        )
        assert result.tool_executions == 1
        assert len(result.checkpoints) == 1

    @pytest.mark.asyncio
    async def test_model_runtime_max_turns_exceeded(self):
        mock_transport = AsyncMock()
        mock_transport.complete = AsyncMock(return_value=ModelTurn(
            content="",
            tool_calls=(ToolCall(id="1", name="test_tool", arguments={}),),
        ))

        async def test_tool(args):
            return "result"

        runtime = ModelRuntime(mock_transport, {"test_tool": test_tool}, max_turns=2)
        with pytest.raises(ValueError, match="AGENT_MAX_TURNS_EXCEEDED"):
            await runtime.run(system_prompt="test", user_message="hello")

    @pytest.mark.asyncio
    async def test_model_runtime_permission_denied(self):
        mock_transport = AsyncMock()
        mock_transport.complete = AsyncMock(side_effect=[
            ModelTurn(content="", tool_calls=(
                ToolCall(id="1", name="dangerous_tool", arguments={}),
            )),
            ModelTurn(content="Done"),
        ])

        async def deny_checker(tool_name, args):
            return ToolPermission.DENY

        runtime = ModelRuntime(
            mock_transport,
            {},
            permission_checker=deny_checker,
        )
        result = await runtime.run(system_prompt="test", user_message="hello")
        assert result.checkpoints[0].approved is False

    @pytest.mark.asyncio
    async def test_model_runtime_duplicate_tool_call_ids(self):
        mock_transport = AsyncMock()
        mock_transport.complete = AsyncMock(return_value=ModelTurn(
            content="",
            tool_calls=(
                ToolCall(id="1", name="tool1", arguments={}),
                ToolCall(id="1", name="tool2", arguments={}),
            ),
        ))

        runtime = ModelRuntime(mock_transport, {})
        with pytest.raises(ValueError, match="MODEL_TOOL_CALL_ID_DUPLICATE"):
            await runtime.run(system_prompt="test", user_message="hello")

    def test_model_runtime_requires_positive_max_turns(self):
        mock_transport = MagicMock()
        with pytest.raises(ValueError, match="max_turns must be positive"):
            ModelRuntime(mock_transport, {}, max_turns=0)


class TestTransport:
    """Tests for model transport adapters."""

    def test_usage_stats(self):
        stats = UsageStats(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        assert stats.prompt_tokens == 10
        assert stats.completion_tokens == 20
        assert stats.total_tokens == 30

    def test_create_transport_openai(self):
        transport = create_transport("openai", api_key="test-key")
        assert isinstance(transport, OpenAITransport)

    def test_create_transport_anthropic(self):
        transport = create_transport("anthropic", api_key="test-key")
        assert isinstance(transport, AnthropicTransport)

    def test_create_transport_unsupported(self):
        with pytest.raises(ValueError, match="Unsupported provider"):
            create_transport("unsupported", api_key="test-key")

    def test_openai_normalize_usage(self):
        transport = OpenAITransport(api_key="test")
        stats = transport.normalize_usage({
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        })
        assert stats.prompt_tokens == 100
        assert stats.completion_tokens == 50
        assert stats.total_tokens == 150

    def test_anthropic_normalize_usage(self):
        transport = AnthropicTransport(api_key="test")
        stats = transport.normalize_usage({
            "input_tokens": 100,
            "output_tokens": 50,
        })
        assert stats.prompt_tokens == 100
        assert stats.completion_tokens == 50
        assert stats.total_tokens == 150

    def test_openai_transport_init(self):
        transport = OpenAITransport(api_key="test", model="gpt-4", base_url="https://api.openai.com/v1")
        assert transport._api_key == "test"
        assert transport._model == "gpt-4"
        assert transport._base_url == "https://api.openai.com/v1"

    def test_anthropic_transport_init(self):
        transport = AnthropicTransport(api_key="test", model="claude-3", base_url="https://api.anthropic.com")
        assert transport._api_key == "test"
        assert transport._model == "claude-3"
        assert transport._base_url == "https://api.anthropic.com"

    def test_parse_json_valid(self):
        from ibreeze.runtime.transport import _parse_json
        result = _parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_invalid(self):
        from ibreeze.runtime.transport import _parse_json
        result = _parse_json("invalid json")
        assert result == {}

    def test_parse_json_non_dict(self):
        from ibreeze.runtime.transport import _parse_json
        result = _parse_json('[1, 2, 3]')
        assert result == {}


class TestEvents:
    """Tests for event system."""

    def test_event_publisher_creates_envelope(self):
        publisher = EventPublisher()
        envelope = publisher.publish(
            EventType.RUN_STARTED,
            run_id="run-1",
            company_id="comp-1",
            employee_id="emp-1",
            payload={"test": True},
        )
        assert isinstance(envelope, EventEnvelope)
        assert envelope.event_type == EventType.RUN_STARTED
        assert envelope.run_id == "run-1"
        assert envelope.sequence == 1

    def test_event_publisher_sequence_increments(self):
        publisher = EventPublisher()
        e1 = publisher.publish(
            EventType.RUN_STARTED,
            run_id="run-1",
            company_id="comp-1",
            employee_id="emp-1",
            payload={},
        )
        e2 = publisher.publish(
            EventType.RUN_COMPLETED,
            run_id="run-1",
            company_id="comp-1",
            employee_id="emp-1",
            payload={},
        )
        assert e2.sequence == e1.sequence + 1

    def test_event_publisher_subscriber(self):
        publisher = EventPublisher()
        received = []
        publisher.subscribe(EventType.RUN_STARTED, lambda e: received.append(e))
        publisher.publish(
            EventType.RUN_STARTED,
            run_id="run-1",
            company_id="comp-1",
            employee_id="emp-1",
            payload={},
        )
        assert len(received) == 1

    def test_event_publisher_unsubscribe(self):
        publisher = EventPublisher()
        received = []
        callback = lambda e: received.append(e)
        publisher.subscribe(EventType.RUN_STARTED, callback)
        publisher.unsubscribe(EventType.RUN_STARTED, callback)
        publisher.publish(
            EventType.RUN_STARTED,
            run_id="run-1",
            company_id="comp-1",
            employee_id="emp-1",
            payload={},
        )
        assert len(received) == 0

    def test_event_publisher_get_sequence(self):
        publisher = EventPublisher()
        publisher.publish(
            EventType.RUN_STARTED,
            run_id="run-1",
            company_id="comp-1",
            employee_id="emp-1",
            payload={},
        )
        seq = publisher.get_sequence("run-1", "comp-1")
        assert seq == 1

    def test_event_publisher_replay_empty(self):
        publisher = EventPublisher()
        result = publisher.replay("run-1", "comp-1")
        assert result == []

    def test_event_publisher_unsubscribe_nonexistent(self):
        publisher = EventPublisher()
        callback = lambda e: None
        publisher.unsubscribe(EventType.RUN_STARTED, callback)

    def test_serialize_deserialize_event(self):
        publisher = EventPublisher()
        envelope = publisher.publish(
            EventType.RUN_STARTED,
            run_id="run-1",
            company_id="comp-1",
            employee_id="emp-1",
            payload={"key": "value"},
            metadata={"source": "test"},
        )
        serialized = serialize_event(envelope)
        deserialized = deserialize_event(serialized)
        assert deserialized.event_id == envelope.event_id
        assert deserialized.event_type == envelope.event_type
        assert deserialized.payload == envelope.payload
        assert deserialized.metadata == envelope.metadata
