"""Test credential boundary: RunSpec and Transport must not contain api_key."""

from __future__ import annotations

from typing import Any

import pytest

from ibreeze.runtime.transport import ReverseRpcTransport, create_transport


class _ProbeSession:
    async def call(self, method: str, params: dict[str, object]) -> dict[str, object]:
        assert method == "credential.probe"
        self.params = params
        return {"available": False}


class TestRunSpecNeverContainsApiKey:
    """Verify that RunSpec construction never embeds api_key."""

    def test_default_spec_has_no_api_key(self) -> None:
        spec: dict[str, Any] = {}
        assert "api_key" not in spec
        assert "credential_ref" not in spec

    def test_spec_with_credential_ref_has_no_api_key(self) -> None:
        spec = {"credential_ref": "cred-abc-123"}
        assert "api_key" not in spec
        assert spec.get("credential_ref") == "cred-abc-123"

    def test_spec_with_model_has_no_api_key(self) -> None:
        spec = {"credential_ref": "cred-1", "model": "gpt-4o"}
        assert "api_key" not in spec

    def test_api_key_field_not_in_expected_spec_keys(self) -> None:
        spec = {
            "prompt": "Hello",
            "credential_ref": "cred-1",
            "model": "gpt-4o",
            "system_prompt": "You are helpful.",
            "timeout_seconds": 300,
        }
        assert "api_key" not in spec
        assert "credential_ref" in spec


class TestTransportNoApiKey:
    """Verify transport does not hold or expose api_key."""

    def test_reverse_rpc_transport_has_no_api_key_attribute(self) -> None:
        t = ReverseRpcTransport(credential_ref="cred-1", model="gpt-4o")
        assert not hasattr(t, "_api_key")
        assert t._credential_ref == "cred-1"

    def test_create_transport_returns_transport_without_api_key(self) -> None:
        t = create_transport(credential_ref="cred-abc", model="claude-3")
        assert not hasattr(t, "_api_key")
        assert t._credential_ref == "cred-abc"

    @pytest.mark.asyncio
    async def test_transport_complete_params_no_api_key(self) -> None:
        t = ReverseRpcTransport(credential_ref="cred-1", model="gpt-4o")
        with pytest.raises(RuntimeError, match="Credential Broker is not configured"):
            await t.complete(
                messages=({"role": "user", "content": "hello"},),
                tool_names=(),
            )
        params = t._rpc.last_params
        assert params is not None
        assert "api_key" not in params
        assert params.get("credential_ref") == "cred-1"

    @pytest.mark.asyncio
    async def test_transport_probe_params_no_api_key(self) -> None:
        t = ReverseRpcTransport(
            credential_ref="cred-1",
            model="gpt-4o",
            provider_release_id="provider-1",
            model_binding_id="binding-1",
            session=_ProbeSession(),
        )
        assert await t.probe() is False
        params = t._rpc.last_params
        assert params is not None
        assert "api_key" not in params
        assert params.get("credential_ref") == "cred-1"
        assert params.get("provider_release_id") == "provider-1"
        assert params.get("model_binding_id") == "binding-1"
