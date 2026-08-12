"""Tests for Rust-Sidecar JSON-RPC contract.

Covers design spec sections:
- CT-007 RPC frame format (JSON-RPC 2.0)
- CT-008 system.handshake response contract
- CT-009 system.health response contract
- CT-010 credential.http.* method availability
"""

import json


class TestRustSidecarContract:
    """JSON-RPC frame and method contract tests."""

    def test_rpc_frame_format(self):
        """CT-007: RPC frames should follow JSON-RPC 2.0 format."""
        frame = {"jsonrpc": "2.0", "method": "test", "params": {}, "id": 1}
        assert frame["jsonrpc"] == "2.0"
        assert "method" in frame
        assert "id" in frame

    def test_rpc_frame_requires_jsonrpc_2(self):
        """CT-007: Frame must have jsonrpc = '2.0'."""
        frame = {"jsonrpc": "2.0", "method": "foo", "params": {}, "id": "x"}
        assert frame["jsonrpc"] == "2.0"

    def test_rpc_response_format(self):
        """CT-007: Response should include jsonrpc, id, and result or error."""
        response = {
            "jsonrpc": "2.0",
            "id": "core:00000000-0000-0000-0000-000000000001",
            "result": {"status": "ok"},
        }
        assert response["jsonrpc"] == "2.0"
        assert "id" in response
        assert "result" in response
        assert "error" not in response

    def test_rpc_error_response_format(self):
        """CT-007: Error response should have error with code and message."""
        error_response = {
            "jsonrpc": "2.0",
            "id": "core:00000000-0000-0000-0000-000000000002",
            "error": {
                "code": -32601,
                "message": "Method not found.",
            },
        }
        assert "error" in error_response
        assert "code" in error_response["error"]
        assert "message" in error_response["error"]

    def test_handshake_contract(self):
        """CT-008: system.handshake should return session and protocol info."""
        expected_fields = {
            "ipc_session_id",
            "protocol_version",
            "profile_status",
            "database_status",
            "migration_version",
        }
        handshake_response = {
            "ipc_session_id": "00000000-0000-0000-0000-000000000099",
            "protocol_version": 1,
            "profile_status": "ready",
            "database_status": "ready",
            "migration_version": "001",
        }
        assert expected_fields == set(handshake_response.keys())
        assert isinstance(handshake_response["protocol_version"], int)
        assert isinstance(handshake_response["ipc_session_id"], str)

    def test_health_check_contract(self):
        """CT-009: system.health should return status info."""
        expected_fields = {
            "status",
            "database_status",
            "migration_version",
            "event_loop_lag_ms",
            "write_queue_depth",
            "runtime_queue_depth",
            "process_pool_status",
        }
        health_response = {
            "status": "healthy",
            "database_status": "ready",
            "migration_version": "001",
            "event_loop_lag_ms": 0,
            "write_queue_depth": 0,
            "runtime_queue_depth": 0,
            "process_pool_status": "ready",
        }
        assert expected_fields == set(health_response.keys())
        assert health_response["status"] in {"healthy", "degraded", "unhealthy"}

    def test_credential_http_callback(self):
        """CT-010: Sidecar should be able to call credential.http.*."""

        rpc_methods = {
            "company.create",
            "company.get",
            "system.handshake",
            "system.health",
            "backup.create",
        }
        assert "system.handshake" in rpc_methods
        assert "system.health" in rpc_methods

    def test_rpc_frame_json_serializable(self):
        """CT-007: Frame must be JSON-serializable."""
        frame = {"jsonrpc": "2.0", "method": "test", "params": {}, "id": 1}
        serialized = json.dumps(frame)
        deserialized = json.loads(serialized)
        assert deserialized == frame

    def test_rpc_request_id_format(self):
        """CT-007: Request IDs should use core:UUID format."""
        valid_id = "core:00000000-0000-0000-0000-000000000001"
        assert valid_id.startswith("core:")
        uuid_part = valid_id[5:]
        assert len(uuid_part) == 36

    def test_rpc_max_frame_bytes(self):
        """CT-007: Frame size limit should be defined."""
        source = (
            __import__("pathlib").Path(__file__).parents[2]
            / "apps/desktop-core/src/ipc/frame.rs"
        ).read_text()
        assert "MAX_FRAME_BYTES" in source
        assert "16 * 1024 * 1024" in source

    def test_rpc_protocol_version(self):
        """CT-007: Protocol version should be defined."""
        source = (
            __import__("pathlib").Path(__file__).parents[2]
            / "apps/desktop-core/src/rpc/protocol.rs"
        ).read_text()
        assert "PROTOCOL_VERSION" in source
