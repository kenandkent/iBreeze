"""Test SSRF protection: transport must not make direct HTTP calls.

All provider network calls must go through the Rust Credential/Egress
Broker via reverse RPC. The Python side must only use reverse RPC methods.
"""

from __future__ import annotations

import pytest

from ibreeze.runtime.transport import ReverseRpcTransport


class _ProbeSession:
    async def call(self, method: str, params: dict[str, object]) -> dict[str, object]:
        assert method == "credential.probe"
        return {"available": False}


class TestNoDirectHttpCalls:
    """Verify transport does not make direct HTTP calls to providers."""

    @pytest.mark.asyncio
    async def test_complete_uses_credential_http_start(self) -> None:
        """complete() must only use credential.http.start reverse method."""
        t = ReverseRpcTransport(credential_ref="cred-1", model="gpt-4o")
        with pytest.raises(RuntimeError, match="Credential Broker is not configured"):
            await t.complete(
                messages=({"role": "user", "content": "hello"},),
                tool_names=(),
            )
        assert t._rpc.last_method == "credential.http.start"

    @pytest.mark.asyncio
    async def test_probe_uses_credential_probe(self) -> None:
        """probe() must only use credential.probe reverse method."""
        t = ReverseRpcTransport(
            credential_ref="cred-1",
            model="gpt-4o",
            provider_release_id="provider-1",
            model_binding_id="binding-1",
            session=_ProbeSession(),
        )
        assert await t.probe() is False
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
        with pytest.raises(RuntimeError, match="Credential Broker is not configured"):
            await t.complete(({"role": "user", "content": "hi"},), ())
        assert t._rpc.last_method in allowed
        probe = ReverseRpcTransport(
            credential_ref="cred-1",
            model="gpt-4o",
            provider_release_id="provider-1",
            model_binding_id="binding-1",
            session=_ProbeSession(),
        )
        assert await probe.probe() is False
        assert probe._rpc.last_method in allowed

    @pytest.mark.asyncio
    async def test_acceptance_persistence_failure_cancels_accepted_request(self) -> None:
        calls: list[str] = []

        class _AcceptedSession:
            async def call(self, method: str, _params: dict[str, object]) -> dict[str, object]:
                calls.append(method)
                if method == "credential.http.start":
                    return {"accepted": True, "stream": True, "request_id": "provider-request-1"}
                if method == "credential.http.cancel":
                    return {"cancelled": True}
                raise AssertionError(method)

        async def fail_persist(_request_id: str) -> None:
            raise RuntimeError("ROUTE_ATTEMPT_ACCEPT_CONFLICT")

        transport = ReverseRpcTransport(
            credential_ref="cred-1",
            model="gpt-4o",
            run_id="run-1",
            session=_AcceptedSession(),
            accepted_callback=fail_persist,
        )
        with pytest.raises(RuntimeError, match="ROUTE_ATTEMPT_ACCEPT_CONFLICT"):
            await transport.complete(({"role": "user", "content": "hello"},), ())
        assert calls == ["credential.http.start", "credential.http.cancel"]
