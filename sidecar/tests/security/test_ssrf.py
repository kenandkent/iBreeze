"""Test SSRF protection: transport must not make direct HTTP calls.

All provider network calls must go through the Rust Credential/Egress
Broker via reverse RPC. The Python side must only use reverse RPC methods.
"""

from __future__ import annotations

import pytest

from ibreeze.runtime.transport import ReverseRpcTransport


class TestNoDirectHttpCalls:
    """Verify transport does not make direct HTTP calls to providers."""

    @pytest.mark.asyncio
    async def test_complete_uses_credential_http_start(self) -> None:
        """complete() must only use credential.http.start reverse method."""
        t = ReverseRpcTransport(credential_ref="cred-1", model="gpt-4o")
        await t.complete(
            messages=({"role": "user", "content": "hello"},),
            tool_names=(),
        )
        assert t._rpc.last_method == "credential.http.start"

    @pytest.mark.asyncio
    async def test_probe_uses_credential_probe(self) -> None:
        """probe() must only use credential.probe reverse method."""
        t = ReverseRpcTransport(credential_ref="cred-1", model="gpt-4o")
        await t.probe()
        assert t._rpc.last_method == "credential.probe"

    def test_transport_has_no_aiohttp_session(self) -> None:
        """Transport must not create or hold an aiohttp session."""
        t = ReverseRpcTransport(credential_ref="cred-1", model="gpt-4o")
        attrs = [a for a in dir(t) if "session" in a.lower() or "http" in a.lower() or "aiohttp" in a.lower()]
        assert len(attrs) == 0, f"Transport should not have HTTP-related attributes: {attrs}"

    def test_transport_has_no_base_url(self) -> None:
        """Transport must not contain provider base URLs."""
        t = ReverseRpcTransport(credential_ref="cred-1", model="gpt-4o")
        assert not hasattr(t, "_base_url")

    def test_transport_has_no_api_key(self) -> None:
        """Transport must not contain api_key."""
        t = ReverseRpcTransport(credential_ref="cred-1", model="gpt-4o")
        assert not hasattr(t, "_api_key")

    @pytest.mark.asyncio
    async def test_allowed_reverse_methods(self) -> None:
        """Verify only credential.* reverse methods are used by transport."""
        t = ReverseRpcTransport(credential_ref="cred-1", model="gpt-4o")
        allowed = {"credential.http.start", "credential.probe"}
        await t.complete(({"role": "user", "content": "hi"},), ())
        assert t._rpc.last_method in allowed
        await t.probe()
        assert t._rpc.last_method in allowed
