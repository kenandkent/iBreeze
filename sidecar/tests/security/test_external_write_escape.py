"""Tests for external write security (Sidecar / workspace_broker side).

Verifies that the workspace_broker constructs proper ExternalWriteRequest
payloads and that the ReverseRpcClient is called with the correct method.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from ibreeze.runtime.workspace_broker import execute_external_write


@pytest.fixture
def mock_rpc() -> AsyncMock:
    rpc = AsyncMock()
    rpc.call.return_value = {
        "approval_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
        "operation": "create_file",
        "target_realpath": "/tmp/test.txt",
        "result_state_sha256": "a" * 64,
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "receipt_sha256": "b" * 64,
    }
    return rpc


def _future_ts() -> str:
    return (datetime.now(UTC) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")


class TestExecuteExternalWrite:
    """execute_external_write builds the correct reverse RPC request."""

    async def test_calls_correct_method(self, mock_rpc: AsyncMock) -> None:
        await execute_external_write(
            mock_rpc,
            approval_id=str(uuid.uuid4()),
            workspace_grant_id=str(uuid.uuid4()),
            run_id=str(uuid.uuid4()),
            operation="create_file",
            target_realpath="/Users/test/output.txt",
            expires_at=_future_ts(),
        )
        mock_rpc.call.assert_awaited_once()
        args, _ = mock_rpc.call.call_args
        assert args[0] == "host.externalWrite.execute"

    async def test_sends_required_fields(self, mock_rpc: AsyncMock) -> None:
        approval_id = str(uuid.uuid4())
        workspace_grant_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        await execute_external_write(
            mock_rpc,
            approval_id=approval_id,
            workspace_grant_id=workspace_grant_id,
            run_id=run_id,
            operation="replace_file",
            target_realpath="/Users/test/existing.txt",
            expected_old_sha256="abc123",
            expires_at=_future_ts(),
        )
        args, _ = mock_rpc.call.call_args
        payload = args[1]
        assert payload["approval_id"] == approval_id
        assert payload["workspace_grant_id"] == workspace_grant_id
        assert payload["run_id"] == run_id
        assert payload["operation"] == "replace_file"
        assert payload["target_realpath"] == "/Users/test/existing.txt"
        assert payload["expected_old_sha256"] == "abc123"

    async def test_optional_fields_default_to_none(self, mock_rpc: AsyncMock) -> None:
        await execute_external_write(
            mock_rpc,
            approval_id=str(uuid.uuid4()),
            workspace_grant_id=str(uuid.uuid4()),
            run_id=str(uuid.uuid4()),
            operation="create_file",
            target_realpath="/tmp/test.txt",
            expires_at=_future_ts(),
        )
        args, _ = mock_rpc.call.call_args
        payload = args[1]
        assert payload["source_relative_path"] is None
        assert payload["source_sha256"] is None
        assert payload["source_size"] is None

    async def test_returns_response_with_receipt(self, mock_rpc: AsyncMock) -> None:
        response = await execute_external_write(
            mock_rpc,
            approval_id=str(uuid.uuid4()),
            workspace_grant_id=str(uuid.uuid4()),
            run_id=str(uuid.uuid4()),
            operation="create_file",
            target_realpath="/tmp/test.txt",
            expires_at=_future_ts(),
        )
        assert "receipt_sha256" in response
        assert "result_state_sha256" in response
        assert "completed_at" in response

    async def test_expired_approval_returns_error(self, mock_rpc: AsyncMock) -> None:
        mock_rpc.call.side_effect = RuntimeError("APPROVAL_EXPIRED")

        with pytest.raises(RuntimeError, match="APPROVAL_EXPIRED"):
            await execute_external_write(
                mock_rpc,
                approval_id=str(uuid.uuid4()),
                workspace_grant_id=str(uuid.uuid4()),
                run_id=str(uuid.uuid4()),
                operation="create_file",
                target_realpath="/tmp/test.txt",
                expires_at="2020-01-01T00:00:00Z",
            )

    async def test_staging_path_validation_in_request(self, mock_rpc: AsyncMock) -> None:
        await execute_external_write(
            mock_rpc,
            approval_id=str(uuid.uuid4()),
            workspace_grant_id=str(uuid.uuid4()),
            run_id=str(uuid.uuid4()),
            operation="replace_file",
            target_realpath="/Users/test/target.txt",
            source_relative_path="staging/source.txt",
            source_sha256="d" * 64,
            source_size=1024,
            expires_at=_future_ts(),
        )
        args, _ = mock_rpc.call.call_args
        payload = args[1]
        assert payload["source_relative_path"] == "staging/source.txt"
        assert payload["source_sha256"] == "d" * 64
        assert payload["source_size"] == 1024
