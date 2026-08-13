"""Canonical routing transport facade used by the Sidecar runtime.

The implementation lives in :class:`RoutedModelTransport` next to the model
transport boundary because it must share the authenticated reverse-RPC,
attempt lifecycle, cancellation, and tool-loop hooks.  This module keeps the
plan's public ``RoutingTransport`` name as a thin compatibility facade; it
contains no second routing algorithm.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ibreeze.runtime.model_loop import ModelTransport
from ibreeze.runtime.transport import RoutedModelTransport


class RoutingTransport(RoutedModelTransport):
    """Compatibility facade for the canonical per-turn routing transport.

    ``base_transport_factory`` is retained only for callers of the pre-v2
    constructor.  All current execution paths use the authenticated Rust
    Broker transport created by ``RoutedModelTransport`` and never call this
    factory, so a legacy factory cannot bypass the Broker boundary.
    """

    def __init__(
        self,
        candidates: list[dict[str, Any]],
        policy: Any,
        *,
        run_id: str,
        session: Any,
        base_transport_factory: Callable[[dict[str, Any], str], ModelTransport] | None = None,
        run_purpose: str = "task_execution",
        input_origin: str = "production",
        **kwargs: Any,
    ) -> None:
        if not candidates:
            raise ValueError("ROUTING_CANDIDATES_REQUIRED")
        mode = getattr(policy, "mode", None)
        if mode is not None:
            mode = getattr(mode, "value", str(mode))
        elif isinstance(policy, dict):
            mode = str(policy.get("mode", "fixed"))
        else:
            mode = "fixed"
        self._legacy_base_transport_factory = base_transport_factory
        routing_policy: dict[str, Any] | None
        if isinstance(policy, dict):
            routing_policy = dict(policy)
        else:
            routing_policy = {
                "mode": str(mode),
                "anchor_candidate_id": str(getattr(policy, "anchor_candidate_id", "")),
                "fallback_order": list(getattr(policy, "fallback_order", ())),
            }
            ensemble = getattr(policy, "ensemble", None)
            if ensemble is not None:
                routing_policy["ensemble"] = {
                    name: getattr(ensemble, name)
                    for name in (
                        "max_proposers",
                        "min_successful_proposers",
                        "proposer_timeout_seconds",
                        "aggregator_timeout_seconds",
                        "proposer_max_retries",
                    )
                }
        if "anchor_candidate_id" not in kwargs:
            kwargs["anchor_candidate_id"] = str(routing_policy.get("anchor_candidate_id", ""))
        super().__init__(
            candidates,
            str(mode),
            run_id,
            session,
            run_purpose=run_purpose,
            input_origin=input_origin,
            routing_policy=routing_policy,
            **kwargs,
        )
