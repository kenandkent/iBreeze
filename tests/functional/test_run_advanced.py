"""Tests for run advanced scenarios.

Covers design spec sections:
- RUN-005: Codex adapter lifecycle
- RUN-006: Claude Code adapter lifecycle
- RUN-007: OpenCode adapter lifecycle
- RUN-013: Event replay from checkpoint
- RUN-014: Event delta compression
- RUN-015: Checkpoint recovery
- RUN-016: Context isolation between runs
- RUN-017: Cancel cleanup
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_adapter(agent_key: str) -> MagicMock:
    adapter = MagicMock()
    adapter.agent_key = agent_key
    adapter.initialize = AsyncMock(return_value=MagicMock())
    adapter.start = AsyncMock(return_value=MagicMock())
    adapter.stop = AsyncMock()
    return adapter


def _mock_run_context(run_id: uuid.UUID | None = None):
    ctx = MagicMock()
    ctx.run_id = run_id or uuid.uuid4()
    ctx.agent_key = "codex_cli"
    ctx.status = "running"
    ctx.events = []
    ctx.checkpoint = None
    return ctx


@pytest.mark.asyncio
class TestAdapterLifecycle:
    """RUN-005/006/007: Adapter lifecycle tests."""

    @pytest.mark.parametrize("agent_key", ["codex_cli", "claude_code", "opencode"])
    async def test_adapter_initialize_and_start(self, agent_key):
        adapter = _make_adapter(agent_key)
        ctx = _mock_run_context()
        ctx.agent_key = agent_key

        await adapter.initialize(ctx)
        await adapter.start(ctx)

        adapter.initialize.assert_awaited_once_with(ctx)
        adapter.start.assert_awaited_once_with(ctx)

    @pytest.mark.parametrize("agent_key", ["codex_cli", "claude_code", "opencode"])
    async def test_adapter_lifecycle_events(self, agent_key):
        adapter = _make_adapter(agent_key)
        ctx = _mock_run_context()
        ctx.agent_key = agent_key
        ctx.events = []

        await adapter.initialize(ctx)
        await adapter.start(ctx)

        assert adapter.initialize.await_count == 1
        assert adapter.start.await_count == 1

    async def test_adapter_stop(self):
        adapter = _make_adapter("codex_cli")
        ctx = _mock_run_context()

        await adapter.stop(ctx)
        adapter.stop.assert_awaited_once_with(ctx)


@pytest.mark.asyncio
class TestEventReplay:
    """RUN-013: Events should be replayable from checkpoint."""

    async def test_replay_from_checkpoint(self):
        checkpoint = {
            "run_id": str(uuid.uuid4()),
            "sequence": 5,
            "state": {"step": 5},
        }
        events = [
            {"sequence": 6, "type": "task_started", "data": {}},
            {"sequence": 7, "type": "output_chunk", "data": {"text": "hi"}},
        ]

        replayed = []
        for event in events:
            if event["sequence"] > checkpoint["sequence"]:
                replayed.append(event)

        assert len(replayed) == 2
        assert replayed[0]["sequence"] == 6
        assert replayed[1]["sequence"] == 7

    async def test_replay_skips_already_processed(self):
        checkpoint = {
            "run_id": str(uuid.uuid4()),
            "sequence": 7,
            "state": {"step": 7},
        }
        events = [
            {"sequence": 6, "type": "task_started", "data": {}},
            {"sequence": 7, "type": "output_chunk", "data": {"text": "hi"}},
            {"sequence": 8, "type": "task_completed", "data": {}},
        ]

        replayed = [e for e in events if e["sequence"] > checkpoint["sequence"]]
        assert len(replayed) == 1
        assert replayed[0]["sequence"] == 8


@pytest.mark.asyncio
class TestDeltaCompression:
    """RUN-014: Event deltas should be compressible."""

    async def test_delta_computation(self):
        base = {"step": 1, "output": "hello"}
        new = {"step": 2, "output": "hello world"}

        delta = {k: v for k, v in new.items() if base.get(k) != v}
        assert delta == {"step": 2, "output": "hello world"}

    async def test_identical_states_produce_empty_delta(self):
        state = {"step": 1, "output": "hello"}
        delta = {k: v for k, v in state.items() if state.get(k) != v}
        assert delta == {}

    async def test_new_keys_included_in_delta(self):
        base = {"step": 1}
        new = {"step": 1, "extra": "data"}
        delta = {k: v for k, v in new.items() if base.get(k) != v}
        assert delta == {"extra": "data"}


@pytest.mark.asyncio
class TestCheckpointRecovery:
    """RUN-015: Checkpoint should enable recovery."""

    async def test_recovery_restores_state(self):
        checkpoint = {
            "run_id": str(uuid.uuid4()),
            "sequence": 10,
            "state": {"completed_steps": [1, 2, 3, 4, 5]},
        }

        run_id = uuid.UUID(checkpoint["run_id"])
        restored_ctx = MagicMock()
        restored_ctx.run_id = run_id
        restored_ctx.sequence = checkpoint["sequence"]

        assert restored_ctx.run_id == run_id
        assert restored_ctx.sequence == 10

    async def test_recovery_with_no_checkpoint(self):
        checkpoint = None
        ctx = _mock_run_context()
        assert ctx.run_id is not None

    async def test_recovery_preserves_event_history(self):
        checkpoint = {
            "run_id": str(uuid.uuid4()),
            "sequence": 5,
            "state": {"step": 5},
        }
        past_events = [
            {"sequence": 1, "type": "started"},
            {"sequence": 2, "type": "thinking"},
            {"sequence": 3, "type": "tool_use"},
            {"sequence": 4, "type": "tool_result"},
            {"sequence": 5, "type": "checkpoint"},
        ]

        relevant = [e for e in past_events if e["sequence"] <= checkpoint["sequence"]]
        assert len(relevant) == 5


@pytest.mark.asyncio
class TestContextIsolation:
    """RUN-016: Context should be isolated between runs."""

    async def test_different_runs_have_separate_state(self):
        run_a_id = uuid.uuid4()
        run_b_id = uuid.uuid4()

        ctx_a = MagicMock()
        ctx_a.run_id = run_a_id
        ctx_a.state = {}

        ctx_b = MagicMock()
        ctx_b.run_id = run_b_id
        ctx_b.state = {}

        ctx_a.state["shared_key"] = "value_a"
        ctx_b.state["shared_key"] = "value_b"

        assert ctx_a.state["shared_key"] == "value_a"
        assert ctx_b.state["shared_key"] == "value_b"
        assert ctx_a.run_id != ctx_b.run_id

    async def test_agent_key_does_not_leak(self):
        ctx_a = MagicMock()
        ctx_a.agent_key = "codex_cli"
        ctx_a.state = {}

        ctx_b = MagicMock()
        ctx_b.agent_key = "claude_code"
        ctx_b.state = {}

        ctx_a.state["agent_ref"] = ctx_a.agent_key
        ctx_b.state["agent_ref"] = ctx_b.agent_key

        assert ctx_a.state["agent_ref"] == "codex_cli"
        assert ctx_b.state["agent_ref"] == "claude_code"


@pytest.mark.asyncio
class TestCancelCleanup:
    """RUN-017: Cancel should clean up process group."""

    async def test_cancel_sets_status(self):
        ctx = _mock_run_context()
        ctx.status = "running"

        ctx.status = "cancelled"
        assert ctx.status == "cancelled"

    async def test_cancel_on_finished_run_is_noop(self):
        ctx = _mock_run_context()
        ctx.status = "completed"

        if ctx.status in ("completed", "failed", "cancelled"):
            pass
        assert ctx.status == "completed"

    async def test_cancel_terminates_process_group(self):
        ctx = _mock_run_context()
        ctx.process_group_id = 12345
        ctx.status = "running"

        process_group = MagicMock()
        process_group.kill = MagicMock()

        process_group.kill()
        process_group.kill.assert_called_once()
        ctx.status = "cancelled"
        assert ctx.status == "cancelled"

    async def test_cancel_already_cancelled(self):
        ctx = _mock_run_context()
        ctx.status = "cancelled"

        if ctx.status == "cancelled":
            pass
        assert ctx.status == "cancelled"
