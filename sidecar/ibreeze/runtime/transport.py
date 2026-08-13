"""Model transport adapters using credential/egress broker via reverse RPC.

All provider network calls go through the Rust Credential/Egress Broker
via reverse RPC. The Sidecar must NOT do direct outbound HTTP to providers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

from ibreeze.observability.routing import get_routing_metrics
from ibreeze.routing.health import HealthState, apply_failure, apply_success
from ibreeze.routing.repository import RoutingRepository
from ibreeze.routing.retry import retry_directive
from ibreeze.routing.types import ProviderFailureKind, RouteRole, RoutingMode
from ibreeze.runtime.model_loop import ModelTurn, ToolCall

logger = logging.getLogger(__name__)

MAX_FRAME_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class UsageStats:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ModelRunCancelledError(RuntimeError):
    """Raised when Rust terminates an in-flight provider request for a run."""


class RouteExecutionSafetyError(RuntimeError):
    """Raised when route authorization or audit persistence cannot complete."""


_REASONING_LEVEL_ORDER = ("low", "medium", "high")
_REASONING_LEVEL_BY_TIER = {"C0": None, "C1": "low", "C2": "medium", "C3": "high"}


def _retry_wait_seconds(kind: ProviderFailureKind, retry_after_ms: int | None) -> float:
    """Return the provider-mandated wait before a same-deployment retry."""
    if kind != ProviderFailureKind.RATE_LIMITED:
        return 0.0
    if retry_after_ms is None:
        return 30.0
    return max(0.0, retry_after_ms / 1000.0)


def _run_deadline_allows_wait(run_deadline_at: str | None, wait_seconds: float) -> bool:
    if run_deadline_at is None:
        return True
    try:
        deadline = datetime.fromisoformat(str(run_deadline_at).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return False
    return wait_seconds < max(0.0, (deadline - datetime.now(UTC)).total_seconds())


def _effective_route_tier(mode: str, classified_tier: str) -> str:
    """Fixed routing keeps the Anchor semantics and does not classify difficulty."""
    return "C0" if mode == RoutingMode.FIXED.value else classified_tier


def _reasoning_level_for_candidate(candidate: dict[str, Any], required_tier: str) -> str | None:
    """Return the smallest supported reasoning level meeting the tier floor."""
    requested = _REASONING_LEVEL_BY_TIER.get(required_tier)
    if requested is None:
        return None
    if not bool(candidate.get("supports_reasoning", False)):
        return "__unavailable__"
    supported = {str(level) for level in candidate.get("reasoning_levels", ())}
    minimum = _REASONING_LEVEL_ORDER.index(requested)
    for level in _REASONING_LEVEL_ORDER[minimum:]:
        if level in supported:
            return level
    return "__unavailable__"


def _stable_score_key(item: tuple[Decimal, dict[str, Any]]) -> tuple[object, ...]:
    """Use the same Decimal/tie-break ordering as the policy engine."""
    score, candidate = item
    try:
        quality = Decimal(
            str(candidate.get("_effective_quality", candidate.get("quality_prior", "0.5000")))
        )
    except Exception:
        quality = Decimal("0.5000")
    try:
        latency = int(candidate.get("latency_prior_ms", 3000))
    except (TypeError, ValueError):
        latency = 3000
    return (
        -score,
        -quality,
        latency,
        str(candidate.get("model_binding_id", "")),
        str(candidate.get("candidate_id", "")),
    )


class ProviderRequestError(RuntimeError):
    """Safe structured provider failure returned by the Rust Broker."""

    def __init__(
        self,
        *,
        kind: str,
        request_id: str | None = None,
        http_status: int | None = None,
        retry_after_ms: int | None = None,
        safe_message: str = "provider request failed",
        visible_content: bool = False,
    ) -> None:
        super().__init__(safe_message)
        self.kind = kind
        self.request_id = request_id
        self.http_status = http_status
        self.retry_after_ms = retry_after_ms
        self.safe_message = safe_message
        self.visible_content = visible_content


@dataclass(slots=True)
class _ActiveModelRequest:
    rpc: ReverseRpcClient
    request_id: str | None = None
    cancel_requested: bool = False
    cancel_sent: bool = False


_active_model_requests: dict[str, dict[str, _ActiveModelRequest]] = {}
_active_model_lock: asyncio.Lock | None = None


async def _get_active_model_lock() -> asyncio.Lock:
    """Create the registry lock in the running event loop.

    Tests and embedded callers may create more than one event loop during the
    process lifetime, so the lock is deliberately lazy instead of being
    constructed at module import time.
    """
    global _active_model_lock
    if _active_model_lock is None:
        _active_model_lock = asyncio.Lock()
    return _active_model_lock


async def _register_active_model_request_with_id(run_id: str, request_key: str, rpc: ReverseRpcClient) -> None:
    lock = await _get_active_model_lock()
    async with lock:
        _active_model_requests.setdefault(run_id, {})[request_key] = _ActiveModelRequest(rpc=rpc)


async def _set_active_model_request_id(run_id: str, request_id: str, request_key: str | None = None) -> bool:
    lock = await _get_active_model_lock()
    async with lock:
        active_map = _active_model_requests.get(run_id, {})
        active = active_map.get(request_key) if request_key else next(iter(active_map.values()), None)
        if active is None:
            return False
        active.request_id = request_id
        return active.cancel_requested


async def _unregister_active_model_request(run_id: str, request_key: str | None = None) -> None:
    lock = await _get_active_model_lock()
    async with lock:
        if request_key is None:
            _active_model_requests.pop(run_id, None)
        else:
            active_map = _active_model_requests.get(run_id, {})
            active_map.pop(request_key, None)
            if not active_map:
                _active_model_requests.pop(run_id, None)


async def cancel_model_run(run_id: str, reason: str = "cancelled by user") -> bool:
    """Cancel the active API Model request owned by ``run_id``.

    The database cancellation is performed by :mod:`runtime.service`; this
    function only controls the provider request.  Marking the request before
    awaiting reverse RPC closes the race where cancellation arrives while the
    ``credential.http.start`` response is still in flight.
    """
    lock = await _get_active_model_lock()
    async with lock:
        active_map = _active_model_requests.get(run_id, {})
        if not active_map:
            return False
        pending: list[tuple[ReverseRpcClient, str]] = []
        for active in active_map.values():
            active.cancel_requested = True
            if active.request_id is not None and not active.cancel_sent:
                active.cancel_sent = True
                pending.append((active.rpc, active.request_id))
    for rpc, request_id in pending:
        await rpc.call("credential.http.cancel", {"run_id": run_id, "request_id": request_id, "reason": reason[:500] or "cancelled"})
    return True


class ModelTransport(ABC):
    """Abstract base for model transport adapters."""

    @abstractmethod
    async def complete(
        self,
        messages: tuple[dict[str, object], ...],
        tool_names: tuple[str, ...],
    ) -> ModelTurn: ...

    @abstractmethod
    async def probe(self) -> bool: ...

    @abstractmethod
    def normalize_usage(self, raw_usage: dict[str, Any]) -> UsageStats: ...


_reverse_rpc_session: Any | None = None


def set_reverse_rpc_session(session: Any | None) -> None:
    """Bind the authenticated Rust↔Sidecar stream for reverse calls."""
    global _reverse_rpc_session
    _reverse_rpc_session = session


def get_reverse_rpc_session() -> Any | None:
    return _reverse_rpc_session


_broker_event_queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}


def _routing_deadline() -> datetime:
    return datetime.now(UTC) + timedelta(seconds=30)


def register_broker_stream(request_id: str) -> asyncio.Queue[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
    _broker_event_queues[request_id] = queue
    return queue


def publish_broker_event(payload: dict[str, Any]) -> None:
    request_id = str(payload.get("request_id", ""))
    queue = _broker_event_queues.get(request_id)
    if queue is None:
        queue = _broker_event_queues.get(str(payload.get("run_id", "")))
    if queue is None:
        return
    try:
        queue.put_nowait(payload)
    except asyncio.QueueFull as exc:
        raise RuntimeError("BROKER_EVENT_BACKPRESSURE") from exc


def unregister_broker_stream(request_id: str) -> None:
    _broker_event_queues.pop(request_id, None)


async def collect_broker_stream(
    request_id: str,
    queue: asyncio.Queue[dict[str, Any]],
    timeout_seconds: float,
    *,
    aliases: tuple[str, ...] = (),
    on_event: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("BROKER_EVENT_TIMEOUT")
            event = await asyncio.wait_for(queue.get(), timeout=remaining)
            if on_event is not None:
                callback_result = on_event(event)
                if callback_result is not None:
                    await callback_result
            kind = event.get("event")
            payload = event.get("payload")
            if kind == "failed":
                safe = payload if isinstance(payload, dict) else {}
                raise ProviderRequestError(
                    kind=str(safe.get("failure_kind", "INVALID_RESPONSE")),
                    request_id=str(safe.get("request_id") or request_id),
                    http_status=int(safe["http_status"]) if safe.get("http_status") is not None else None,
                    retry_after_ms=int(safe["retry_after_ms"]) if safe.get("retry_after_ms") is not None else None,
                    safe_message=str(safe.get("safe_message", "provider request failed"))[:200],
                    visible_content=bool(safe.get("visible_content", bool(events))),
                )
            if kind == "completed":
                if isinstance(payload, dict) and set(payload) - {"status"}:
                    return payload
                return {"events": events}
            if isinstance(payload, dict):
                events.append(payload)
            if len(events) > 4096:
                raise RuntimeError("BROKER_EVENT_LIMIT_EXCEEDED")
    finally:
        unregister_broker_stream(request_id)
        for alias in aliases:
            unregister_broker_stream(alias)


class ReverseRpcClient:
    """Client for the authenticated Rust reverse-RPC session.

    Production code receives the already-authenticated :class:`IpcSession`
    through the lifecycle binding and never opens a second connection to the
    Sidecar UDS.
    """

    def __init__(self, session: Any | None = None) -> None:
        self._session = session
        self.last_method: str | None = None
        self.last_params: dict[str, Any] | None = None

    async def _ensure_connected(self) -> None:
        if self._session is not None:
            return
        if _reverse_rpc_session is not None:
            self._session = _reverse_rpc_session
            return

    async def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.last_method = method
        self.last_params = params

        await self._ensure_connected()
        if self._session is not None:
            result = await self._session.call(method, params)
            return result if isinstance(result, dict) else {}

        logger.warning("ReverseRpcClient has no authenticated Rust session for method=%s", method)
        raise RuntimeError(
            "RUST_REVERSE_SESSION_UNAVAILABLE: bind the authenticated IPC session before executing reverse RPC; "
            "Credential Broker is not configured for this Sidecar instance"
        )


class ReverseRpcTransport(ModelTransport):
    """Transport that goes through the Credential/Egress Broker via reverse RPC.

    Never holds an api_key directly - only a credential_ref that the Rust
    side resolves into actual credentials for the provider.

    Uses :class:`ReverseRpcClient` over the authenticated IPC session.
    """

    def __init__(
        self,
        credential_ref: str,
        model: str,
        run_id: str = "",
        provider_release_id: str = "",
        model_binding_id: str = "",
        provider_protocol: str = "openai_chat_completions",
        credential_secret_version: int = 1,
        execution_snapshot_id: str = "",
        route_decision_id: str = "",
        route_attempt_id: str = "",
        candidate_id: str = "",
        route_role: str = "",
        reasoning_level: str | None = None,
        run_deadline_at: str | None = None,
        allow_tool_execution: bool = True,
        accepted_callback: Callable[[str], Awaitable[None]] | None = None,
        session: Any | None = None,
    ) -> None:
        self._credential_ref = credential_ref
        self._model = model
        self._run_id = run_id
        self._provider_release_id = provider_release_id
        self._model_binding_id = model_binding_id
        if provider_protocol not in {
            "openai_responses",
            "anthropic_messages",
            "openai_chat_completions",
        }:
            raise ValueError("PROVIDER_PROTOCOL_INVALID")
        self._provider_protocol = provider_protocol
        self._credential_secret_version = credential_secret_version
        self._execution_snapshot_id = execution_snapshot_id
        self._route_decision_id = route_decision_id
        self._route_attempt_id = route_attempt_id
        self._candidate_id = candidate_id
        self._route_role = route_role
        self._reasoning_level = reasoning_level
        self._run_deadline_at = run_deadline_at
        self._allow_tool_execution = allow_tool_execution
        self._accepted_callback = accepted_callback
        self._streaming_callback: Callable[[], Awaitable[None]] | None = None
        self._rpc = ReverseRpcClient(session=session)

    async def complete(
        self,
        messages: tuple[dict[str, object], ...],
        tool_names: tuple[str, ...],
    ) -> ModelTurn:
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        provider_deadline = now + timedelta(minutes=5)
        if self._run_deadline_at:
            try:
                run_deadline = datetime.fromisoformat(str(self._run_deadline_at).replace("Z", "+00:00")).astimezone(UTC)
            except ValueError as exc:
                raise ValueError("RUN_DEADLINE_INVALID") from exc
            provider_deadline = min(provider_deadline, run_deadline)
        if provider_deadline <= now:
            raise ValueError("RUN_DEADLINE_EXCEEDED")
        remaining_seconds = max(0.1, (provider_deadline - now).total_seconds())
        deadline_at = provider_deadline.isoformat().replace("+00:00", "Z")
        queue = register_broker_stream(self._run_id)
        request_id: str | None = None
        cancel_sent = False
        request_key = str(uuid4())
        await _register_active_model_request_with_id(self._run_id, request_key, self._rpc)
        try:
            accepted = await self._rpc.call(
                "credential.http.start",
                {
                    "run_id": self._run_id,
                    **({"execution_snapshot_id": self._execution_snapshot_id} if self._execution_snapshot_id else {}),
                    **({"route_decision_id": self._route_decision_id} if self._route_decision_id else {}),
                    **({"route_attempt_id": self._route_attempt_id} if self._route_attempt_id else {}),
                    **({"candidate_id": self._candidate_id} if self._candidate_id else {}),
                    **({"route_role": self._route_role} if self._route_role else {}),
                    "credential_ref": self._credential_ref,
                    "credential_secret_version": self._credential_secret_version,
                    "provider_release_id": self._provider_release_id,
                    "model_binding_id": self._model_binding_id,
                    "operation": "model_turn",
                    "request": _build_provider_request(
                        self._provider_protocol,
                        messages,
                        tool_names,
                        reasoning_level=self._reasoning_level,
                        tools_are_suggestions=not self._allow_tool_execution,
                    ),
                    "deadline_at": deadline_at,
                },
            )
            if accepted.get("accepted") is not True or accepted.get("stream") is not True:
                raise RuntimeError("BROKER_REQUEST_NOT_ACCEPTED")
            request_id = accepted.get("request_id")
            if not isinstance(request_id, str) or not request_id:
                raise RuntimeError("BROKER_REQUEST_ID_MISSING")
            if self._accepted_callback is not None:
                try:
                    await self._accepted_callback(request_id)
                except Exception:
                    # The Broker has already accepted the physical request,
                    # but the durable Attempt boundary failed.  Cancel before
                    # returning the write error so an untracked provider call
                    # cannot continue or produce a side effect.
                    try:
                        await self._rpc.call(
                            "credential.http.cancel",
                            {
                                "run_id": self._run_id,
                                "request_id": request_id,
                                "reason": "route attempt acceptance persistence failed",
                            },
                        )
                        cancel_sent = True
                    except Exception:
                        logger.exception("failed to cancel provider request after Attempt acceptance failure")
                    raise
            cancel_requested = await _set_active_model_request_id(self._run_id, request_id, request_key)
            _broker_event_queues[request_id] = queue
            if cancel_requested:
                await cancel_model_run(self._run_id, "cancelled before provider request was ready")

            async def mark_streaming(event: dict[str, Any]) -> None:
                # A completed/failed event is terminal, not a stream start.
                # The first non-terminal event is the durable boundary after
                # which transparent fallback is forbidden.
                if event.get("event") in {"completed", "failed"}:
                    return
                callback = self._streaming_callback
                if callback is not None:
                    await callback()

            result = await collect_broker_stream(
                self._run_id,
                queue,
                min(300.0, remaining_seconds),
                aliases=(request_id,),
                on_event=mark_streaming,
            )
            if result.get("state") == "cancelled":
                raise ModelRunCancelledError("MODEL_RUN_CANCELLED")
        except Exception:
            unregister_broker_stream(self._run_id)
            if request_id is not None:
                unregister_broker_stream(request_id)
                if not cancel_sent:
                    try:
                        await self._rpc.call(
                            "credential.http.cancel",
                            {
                                "run_id": self._run_id,
                                "request_id": request_id,
                                "reason": "route transport failed before terminal result",
                            },
                        )
                        cancel_sent = True
                    except Exception:
                        logger.exception("failed to cancel provider request after route transport failure")
            raise
        finally:
            await _unregister_active_model_request(self._run_id, request_key)
        normalized = _normalize_model_response(result)
        return ModelTurn(
            content=normalized.get("content", ""),
            tool_calls=tuple(
                ToolCall(
                    id=tc["id"],
                    name=tc["name"],
                    arguments=tc.get("arguments", {}),
                )
                for tc in normalized.get("tool_calls", [])
            ),
            usage=normalized.get("usage", {}),
        )

    async def probe(self) -> bool:
        if not self._provider_release_id or not self._model_binding_id:
            return False
        result = await self._rpc.call(
            "credential.probe",
            {
                "credential_ref": self._credential_ref,
                "provider_release_id": self._provider_release_id,
                "model_binding_id": self._model_binding_id,
            },
        )
        return result.get("available", result.get("status") == "ok") is True

    def normalize_usage(self, raw_usage: dict[str, Any]) -> UsageStats:
        return UsageStats(
            prompt_tokens=raw_usage.get("prompt_tokens", 0),
            completion_tokens=raw_usage.get("completion_tokens", 0),
            total_tokens=raw_usage.get("total_tokens", 0),
        )


class RoutedModelTransport(ModelTransport):
    """Deterministic per-turn router for API Model profiles.

    Candidate metadata is supplied by the immutable Execution Snapshot. The
    router never consults the mutable catalog while a run is executing.
    """

    def __init__(
        self,
        candidates: list[dict[str, Any]],
        mode: str,
        run_id: str,
        session: Any,
        *,
        execution_snapshot_id: str = "",
        run_purpose: str = "task_execution",
        input_origin: str = "production",
        run_deadline_at: str | None = None,
        artifact_type: str | None = None,
        required_capability_tags: tuple[str, ...] = (),
        attachment_types: tuple[str, ...] = (),
        prior_tool_failures: int = 0,
        verification_failures: int = 0,
        open_blocker_high_count: int = 0,
        read_pool: Any | None = None,
        write_queue: Any | None = None,
        company_id: str = "",
        anchor_candidate_id: str = "",
        routing_policy: dict[str, Any] | None = None,
        candidate_bindings_json: str | None = None,
        candidate_bindings_sha256: str | None = None,
    ) -> None:
        if not candidates:
            raise ValueError("ROUTING_CANDIDATES_REQUIRED")
        if input_origin not in {"production", "evaluation"}:
            raise ValueError("ROUTING_INPUT_ORIGIN_INVALID")
        self._candidates = [dict(item) for item in candidates]
        self._mode = mode
        self._active_mode = mode
        self._run_id = run_id
        self._session = session
        self._execution_snapshot_id = execution_snapshot_id
        self._run_purpose = run_purpose
        self._input_origin = input_origin
        self._run_deadline_at = run_deadline_at
        self._artifact_type = artifact_type
        self._required_capability_tags = tuple(required_capability_tags)
        self._attachment_types = tuple(attachment_types)
        self._prior_tool_failures = prior_tool_failures
        self._verification_failures = verification_failures
        self._open_blocker_high_count = open_blocker_high_count
        self._read_pool = read_pool
        self._write_queue = write_queue
        self._company_id = company_id
        self._anchor_candidate_id = anchor_candidate_id or str(self._candidates[0].get("candidate_id", ""))
        self._routing_policy = dict(routing_policy or {})
        self._candidate_bindings_json = candidate_bindings_json
        self._candidate_bindings_sha256 = candidate_bindings_sha256
        self._repository = RoutingRepository()
        self._health: dict[str, HealthState] = {}
        self._last_transport: ReverseRpcTransport | None = None
        self._turn_index = 0
        # Snapshot authorization is immutable for the complete Run.  Only
        # Decision authorization is registered once per turn.
        self._snapshot_registered = False
        # The Snapshot lease uses the Run/Profile deadline.  The optional
        # value preserves legacy callers that do not provide a deadline.
        self._snapshot_deadline_at: str | None = run_deadline_at
        self._active_tier = "C0"
        self._previous_tier: str | None = None
        self._previous_confidence: float | None = None
        self._provider_failures = 0
        self._last_context: Any | None = None

    def _transport_for(
        self,
        candidate: dict[str, Any],
        suffix: str = "",
        *,
        route_decision_id: str = "",
        route_role: str = "",
        attempt_id: str = "",
        reasoning_level: str | None = None,
    ) -> ReverseRpcTransport:
        return ReverseRpcTransport(
            credential_ref=str(candidate["credential_ref"]),
            model=str(candidate.get("provider_model_name") or candidate.get("model_id") or ""),
            # The Rust reverse contract requires the original AgentRun UUID.
            # Candidate/attempt uniqueness is carried by route_attempt_id;
            # suffixing run_id would make the request fail deserialization and
            # would also break Run-scoped cancellation.
            run_id=self._run_id,
            provider_release_id=str(candidate["provider_release_id"]),
            model_binding_id=str(candidate["model_binding_id"]),
            provider_protocol=str(candidate["provider_protocol"]),
            credential_secret_version=int(candidate.get("credential_secret_version", 1)),
            execution_snapshot_id=self._execution_snapshot_id,
            route_decision_id=route_decision_id,
            route_attempt_id=attempt_id or (str(uuid4()) if route_decision_id else ""),
            candidate_id=str(candidate.get("candidate_id", "")),
            route_role=route_role,
            reasoning_level=(reasoning_level if reasoning_level is not None else self._candidate_reasoning_level(candidate)),
            run_deadline_at=self._run_deadline_at,
            allow_tool_execution=route_role != "proposer",
            session=self._session,
        )

    def _candidate_reasoning_level(self, candidate: dict[str, Any]) -> str | None:
        level = _reasoning_level_for_candidate(candidate, self._active_tier)
        return None if level == "__unavailable__" else level

    async def _persist_decision(
        self,
        decision_id: str,
        selections: list[tuple[dict[str, Any], str]],
        *,
        tier: str = "C0",
        confidence: float = 0.6,
        aggregator_candidate_id: str | None = None,
        context: Any | None = None,
        policy_trail: tuple[dict[str, object], ...] = (),
    ) -> None:
        if self._write_queue is None or not self._company_id or not self._execution_snapshot_id:
            return
        selected_kind = "ensemble" if any(role in {"proposer", "aggregator"} for _candidate, role in selections) else "single"
        bindings = [{"candidate_id": str(candidate["candidate_id"]), "role": role} for candidate, role in selections]
        fingerprint = context.fingerprint() if context is not None else __import__("hashlib").sha256(
            f"{self._run_id}:{self._turn_index}".encode()
        ).hexdigest()

        async def execute(db: Any) -> None:
            await self._repository.create_decision(
                db,
                decision_id=decision_id,
                company_id=self._company_id,
                run_id=self._run_id,
                turn_index=self._turn_index,
                execution_snapshot_id=self._execution_snapshot_id,
                routing_mode=RoutingMode(self._active_mode),
                classifier_version="rules-v1",
                input_fingerprint=fingerprint,
                required_tier=tier,
                confidence=confidence,
                selected_kind=selected_kind,
                selected_bindings=bindings,
                policy_trail=list(policy_trail),
                aggregator_candidate_id=aggregator_candidate_id,
            )

        try:
            await self._write_queue.submit("routing.decision.create", uuid4(), _routing_deadline(), execute)
        except Exception as exc:
            raise RouteExecutionSafetyError("ROUTING_AUDIT_PERSISTENCE_FAILED") from exc

    async def _transition_decision(self, decision_id: str, expected: str, target: str) -> None:
        if self._write_queue is None or not self._company_id or not self._execution_snapshot_id:
            return

        async def execute(db: Any) -> None:
            changed = await self._repository.transition_decision(db, decision_id, expected, target)
            if not changed and expected == "planned":
                raise RuntimeError("ROUTE_DECISION_STATE_CONFLICT")

        try:
            await self._write_queue.submit("routing.decision.transition", uuid4(), _routing_deadline(), execute)
        except Exception as exc:
            raise RouteExecutionSafetyError("ROUTING_AUDIT_PERSISTENCE_FAILED") from exc

    async def _persist_health(self, candidate: dict[str, Any], state: HealthState) -> None:
        if self._write_queue is None or not self._company_id:
            return
        import hashlib

        async def execute(db: Any) -> None:
            await self._repository.upsert_health(
                db,
                company_id=self._company_id,
                provider_release_id=str(candidate.get("provider_release_id", "")),
                model_binding_id=str(candidate.get("model_binding_id", "")),
                credential_ref_sha256=hashlib.sha256(str(candidate.get("credential_ref", "")).encode("utf-8")).hexdigest(),
                availability_state=state.availability_state,
                consecutive_strikes=state.consecutive_strikes,
                benched_until=state.benched_until.isoformat().replace("+00:00", "Z") if state.benched_until else None,
                last_failure_kind=state.last_failure_kind,
                last_failure_at=state.last_failure_at.isoformat().replace("+00:00", "Z") if state.last_failure_at else None,
                last_success_at=state.last_success_at.isoformat().replace("+00:00", "Z") if state.last_success_at else None,
            )

        try:
            await self._write_queue.submit("routing.health.upsert", uuid4(), _routing_deadline(), execute)
        except Exception as exc:
            raise RouteExecutionSafetyError("ROUTING_HEALTH_PERSISTENCE_FAILED") from exc

    async def _record_provider_failure(
        self,
        candidate: dict[str, Any],
        kind: ProviderFailureKind,
        *,
        retry_after_ms: int | None = None,
    ) -> None:
        """Apply and persist one structured provider failure consistently."""
        self._provider_failures += 1
        state = apply_failure(
            self._health.get(str(candidate.get("candidate_id")), HealthState()),
            kind,
            retry_after_seconds=(math.ceil(retry_after_ms / 1000) if retry_after_ms is not None else None),
        )
        self._health[str(candidate.get("candidate_id"))] = state
        await self._persist_health(candidate, state)

    async def _transition_attempt_terminal(
        self,
        attempt_id: str,
        target_status: str,
        *,
        failure_kind: ProviderFailureKind | None = None,
        http_status: int | None = None,
        latency_ms: int | None = None,
    ) -> None:
        """Move an attempt to one terminal state exactly once.

        A provider can finish before the acceptance callback is committed, so
        recovery must CAS all three non-terminal states in order.  The helper
        deliberately treats an already-terminal attempt as idempotent.
        """
        if self._write_queue is None or not attempt_id:
            return

        async def persist(db: Any) -> None:
            for expected in ("created", "accepted", "streaming"):
                if await self._repository.transition_attempt(
                    db,
                    attempt_id,
                    expected,
                    target_status,
                    failure_kind=failure_kind,
                    http_status=http_status,
                    latency_ms=latency_ms,
                ):
                    return

        try:
            await self._write_queue.submit(f"routing.attempt.{target_status}", uuid4(), _routing_deadline(), persist)
        except Exception as exc:
            raise RouteExecutionSafetyError("ROUTING_AUDIT_PERSISTENCE_FAILED") from exc

    async def _execute_candidate(
        self,
        transport: ReverseRpcTransport,
        candidate: dict[str, Any],
        decision_id: str,
        role: str,
        sequence: int,
        messages: tuple[dict[str, object], ...],
        tool_names: tuple[str, ...],
        *,
        cancel_status: str = "cancelled",
    ) -> ModelTurn:
        import time

        attempt_id = transport._route_attempt_id
        if self._write_queue is not None and self._company_id and self._execution_snapshot_id and attempt_id:

            async def create(db: Any) -> None:
                await self._repository.create_attempt(
                    db,
                    attempt_id=attempt_id,
                    route_decision_id=decision_id,
                    company_id=self._company_id,
                    run_id=self._run_id,
                    execution_snapshot_id=self._execution_snapshot_id,
                    attempt_sequence=sequence,
                    role=RouteRole(role),
                    candidate_id=str(candidate["candidate_id"]),
                    provider_release_id=str(candidate["provider_release_id"]),
                    model_binding_id=str(candidate["model_binding_id"]),
                    credential_ref_sha256=__import__("hashlib").sha256(str(candidate["credential_ref"]).encode()).hexdigest(),
                )

            try:
                await self._write_queue.submit("routing.attempt.create", uuid4(), _routing_deadline(), create)
            except Exception as exc:
                raise RouteExecutionSafetyError("ROUTING_AUDIT_PERSISTENCE_FAILED") from exc

        async def accepted(request_id: str) -> None:
            if self._write_queue is None or not attempt_id:
                return

            async def persist(db: Any) -> None:
                await self._repository.bind_attempt_request(db, attempt_id=attempt_id, request_id=request_id)
                changed = await self._repository.transition_attempt(db, attempt_id, "created", "accepted")
                if not changed:
                    raise RuntimeError("ROUTE_ATTEMPT_ACCEPT_CONFLICT")

            try:
                await self._write_queue.submit("routing.attempt.accepted", uuid4(), _routing_deadline(), persist)
            except Exception as exc:
                raise RouteExecutionSafetyError("ROUTING_AUDIT_PERSISTENCE_FAILED") from exc

        transport._accepted_callback = accepted

        async def streaming() -> None:
            if self._write_queue is None or not attempt_id:
                return

            async def persist(db: Any) -> None:
                # A terminal event can race this callback; CAS makes the
                # transition idempotent and never reopens a terminal attempt.
                await self._repository.transition_attempt(db, attempt_id, "accepted", "streaming")

            try:
                await self._write_queue.submit("routing.attempt.streaming", uuid4(), _routing_deadline(), persist)
            except Exception as exc:
                raise RouteExecutionSafetyError("ROUTING_AUDIT_PERSISTENCE_FAILED") from exc

        transport._streaming_callback = streaming
        started = time.monotonic()
        try:
            result = await transport.complete(messages, tool_names)
            get_routing_metrics().record_attempt(
                role=role,
                provider=str(candidate.get("provider_release_id", "")),
                model=str(candidate.get("model_binding_id", "")),
                status="succeeded",
                latency_ms=int((time.monotonic() - started) * 1000),
            )
        except ModelRunCancelledError:
            get_routing_metrics().record_attempt(
                role=role,
                provider=str(candidate.get("provider_release_id", "")),
                model=str(candidate.get("model_binding_id", "")),
                status="cancelled",
                latency_ms=int((time.monotonic() - started) * 1000),
            )
            await self._transition_attempt_terminal(
                attempt_id,
                "cancelled",
                latency_ms=int((time.monotonic() - started) * 1000),
            )
            raise
        except asyncio.CancelledError:
            get_routing_metrics().record_attempt(
                role=role,
                provider=str(candidate.get("provider_release_id", "")),
                model=str(candidate.get("model_binding_id", "")),
                status="cancelled",
                latency_ms=int((time.monotonic() - started) * 1000),
            )
            latency_ms = int((time.monotonic() - started) * 1000)
            if cancel_status == "timed_out":
                timeout_error = ProviderRequestError(
                    kind=ProviderFailureKind.TIMEOUT.value,
                    safe_message="provider request timed out",
                )
                await self._transition_attempt_terminal(
                    attempt_id,
                    "timed_out",
                    failure_kind=ProviderFailureKind.TIMEOUT,
                    latency_ms=latency_ms,
                )
                raise timeout_error
            await self._transition_attempt_terminal(attempt_id, "cancelled", latency_ms=latency_ms)
            raise
        except TimeoutError as exc:
            # ``collect_broker_stream`` intentionally exposes the standard
            # timeout so this boundary is the single place that classifies it
            # into the persisted twelve-value failure taxonomy.
            structured = ProviderRequestError(
                kind=ProviderFailureKind.TIMEOUT.value,
                safe_message="provider request timed out",
            )
            get_routing_metrics().record_attempt(
                role=role,
                provider=str(candidate.get("provider_release_id", "")),
                model=str(candidate.get("model_binding_id", "")),
                status="failed",
                failure_kind=structured.kind,
                latency_ms=int((time.monotonic() - started) * 1000),
            )
            await self._transition_attempt_terminal(
                attempt_id,
                "timed_out",
                failure_kind=ProviderFailureKind.TIMEOUT,
                latency_ms=int((time.monotonic() - started) * 1000),
            )
            raise structured from exc
        except Exception as exc:
            failure_kind_value = exc.kind if isinstance(exc, ProviderRequestError) else "INVALID_RESPONSE"
            get_routing_metrics().record_attempt(
                role=role,
                provider=str(candidate.get("provider_release_id", "")),
                model=str(candidate.get("model_binding_id", "")),
                status="failed",
                failure_kind=str(failure_kind_value),
                latency_ms=int((time.monotonic() - started) * 1000),
            )
            failure_kind = None
            http_status = None
            if isinstance(exc, ProviderRequestError):
                failure_kind = (
                    ProviderFailureKind(exc.kind)
                    if exc.kind in ProviderFailureKind._value2member_map_
                    else ProviderFailureKind.INVALID_RESPONSE
                )
                http_status = exc.http_status
            await self._transition_attempt_terminal(
                attempt_id,
                "failed",
                failure_kind=failure_kind,
                http_status=http_status,
                latency_ms=int((time.monotonic() - started) * 1000),
            )
            raise
        if self._write_queue is not None and attempt_id:

            async def succeed(db: Any) -> None:
                usage = result.usage if isinstance(result.usage, dict) else {}
                stats = {
                    "input_tokens": int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0),
                    "output_tokens": int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0),
                    "total_tokens": int(usage.get("total_tokens", 0) or 0),
                }
                for expected in ("created", "accepted", "streaming"):
                    if await self._repository.transition_attempt(
                        db,
                        attempt_id,
                        expected,
                        "succeeded",
                        latency_ms=int((time.monotonic() - started) * 1000),
                        input_tokens=stats["input_tokens"],
                        output_tokens=stats["output_tokens"],
                        total_tokens=stats["total_tokens"],
                    ):
                        break

            try:
                await self._write_queue.submit("routing.attempt.succeeded", uuid4(), _routing_deadline(), succeed)
            except Exception as exc:
                raise RouteExecutionSafetyError("ROUTING_AUDIT_PERSISTENCE_FAILED") from exc
        return result

    async def _register_authorization(self, decision_id: str, selections: list[tuple[dict[str, Any], str]]) -> None:
        if not self._execution_snapshot_id:
            return
        import hashlib
        from datetime import UTC, datetime, timedelta

        # Preserve the exact immutable v2 bytes loaded from the Execution
        # Snapshot. Re-serializing a reduced authorization view here would
        # change the hash and break the snapshot immutability guarantee.
        if self._candidate_bindings_json:
            snapshot_json = self._candidate_bindings_json
            snapshot_hash = self._candidate_bindings_sha256 or hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
        else:
            # Legacy fixed snapshots have no raw v2 field. Keep their minimal
            # compatibility projection isolated from new API Model runs.
            authorized = [
                {
                    "candidate_id": str(candidate["candidate_id"]),
                    "provider_release_id": str(candidate["provider_release_id"]),
                    "model_binding_id": str(candidate["model_binding_id"]),
                    "credential_ref": str(candidate["credential_ref"]),
                    "credential_secret_version": int(candidate.get("credential_secret_version", 1)),
                    "eligible_roles": list(candidate.get("eligible_roles", [])),
                    "request_defaults_sha256": str(candidate.get("request_defaults_sha256", "")),
                }
                for candidate in self._candidates
            ]
            snapshot_json = json.dumps(authorized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            snapshot_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
        rpc = ReverseRpcClient(session=self._session)
        if not self._snapshot_registered:
            if self._snapshot_deadline_at is None:
                self._snapshot_deadline_at = (datetime.now(UTC) + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
            await rpc.call(
                "routing.snapshot.register",
                {
                    "execution_snapshot_id": self._execution_snapshot_id,
                    "run_id": self._run_id,
                    "candidate_bindings_json": snapshot_json,
                    "candidate_bindings_sha256": snapshot_hash,
                    "run_deadline_at": self._snapshot_deadline_at,
                },
            )
            self._snapshot_registered = True
        await rpc.call(
            "routing.decision.register",
            {
                "route_decision_id": decision_id,
                "run_id": self._run_id,
                "execution_snapshot_id": self._execution_snapshot_id,
                "turn_index": self._turn_index,
                "selections": [{"candidate_id": str(candidate["candidate_id"]), "role": role} for candidate, role in selections],
            },
        )

    async def _resolve_override(self) -> str | None:
        """Read the per-run control row once; never reread Profile/Catalog."""
        if self._read_pool is None or not self._company_id:
            return None
        row = await self._read_pool.query_one(
            "SELECT override_mode FROM routing_run_controls WHERE company_id=? AND run_id=?",
            (self._company_id, self._run_id),
        )
        return str(row.get("override_mode")) if row and row.get("override_mode") is not None else None

    def _mode_for_override(self, override: str | None) -> str:
        if override is None:
            return self._mode
        return {
            "force_fixed": RoutingMode.FIXED.value,
            "force_single": RoutingMode.SMART_SINGLE.value,
            "force_ensemble": RoutingMode.SELECTIVE_ENSEMBLE.value,
        }.get(override, RoutingMode.FIXED.value)

    async def _resolve_mode(self) -> str:
        """Resolve the per-run override without rereading mutable catalog data."""
        return self._mode_for_override(await self._resolve_override())

    async def revoke_snapshot(self) -> None:
        """Revoke the Rust lease when the owning Run leaves execution."""
        if not self._execution_snapshot_id or not self._snapshot_registered:
            return
        await ReverseRpcClient(session=self._session).call(
            "routing.snapshot.revoke",
            {"run_id": self._run_id},
        )
        self._snapshot_registered = False

    async def _prepare_decision(
        self,
        decision_id: str,
        selections: list[tuple[dict[str, Any], str]],
        *,
        tier: str = "C0",
        confidence: float = 0.6,
        aggregator_candidate_id: str | None = None,
        context: Any | None = None,
        policy_trail: tuple[dict[str, object], ...] = (),
    ) -> None:
        await self._persist_decision(
            decision_id,
            selections,
            tier=tier,
            confidence=confidence,
            aggregator_candidate_id=aggregator_candidate_id,
            context=context,
            policy_trail=policy_trail,
        )
        await self._register_authorization(decision_id, selections)
        await self._transition_decision(decision_id, "planned", "executing")
        get_routing_metrics().inc(
            "routing_decisions_total",
            labels={
                "mode": self._active_mode,
                "tier": tier,
                "kind": "ensemble" if any(role in {"proposer", "aggregator"} for _candidate, role in selections) else "single",
                "status": "executing",
            },
        )

    def _fallback_candidates(
        self,
        ranked: list[tuple[Decimal, dict[str, Any]]],
        primary: dict[str, Any],
        *,
        failure_kind: ProviderFailureKind | None = None,
        excluded_candidate_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return the policy-defined fallback chain, then stable ranked rest."""
        if failure_kind in {ProviderFailureKind.BAD_REQUEST, ProviderFailureKind.POLICY_REFUSAL}:
            return []
        excluded = excluded_candidate_ids or set()

        def allowed(candidate: dict[str, Any]) -> bool:
            candidate_id = str(candidate.get("candidate_id"))
            if (
                candidate is primary
                or candidate_id in excluded
                or "fallback" not in candidate.get("eligible_roles", ())
                or not self._health.get(candidate_id, HealthState()).is_eligible()
            ):
                return False
            if failure_kind == ProviderFailureKind.CONTEXT_OVERFLOW:
                return int(candidate.get("context_window", 0)) > int(primary.get("context_window", 0))
            if failure_kind in {ProviderFailureKind.AUTH_INVALID, ProviderFailureKind.INSUFFICIENT_CREDITS}:
                same_provider = str(candidate.get("provider_release_id")) == str(primary.get("provider_release_id"))
                same_credential = str(candidate.get("credential_ref")) == str(primary.get("credential_ref"))
                return not (same_provider and same_credential)
            return True

        by_id = {str(candidate.get("candidate_id")): candidate for _score, candidate in ranked if allowed(candidate)}
        ordered: list[dict[str, Any]] = []
        for candidate_id in self._routing_policy.get("fallback_order", ()):
            candidate = by_id.pop(str(candidate_id), None)
            if candidate is not None:
                ordered.append(candidate)
        ordered.extend(
            candidate
            for _score, candidate in ranked
            if str(candidate.get("candidate_id")) in by_id and by_id.pop(str(candidate.get("candidate_id")), None) is not None
        )
        return ordered

    async def complete(
        self,
        messages: tuple[dict[str, object], ...],
        tool_names: tuple[str, ...],
    ) -> ModelTurn:
        from ibreeze.routing.classifier import RulesV1Classifier
        from ibreeze.routing.config import startup_config
        from ibreeze.routing.context import build_routing_context
        from ibreeze.routing.engine import score_candidate
        from ibreeze.routing.ensemble import select_proposer_candidates, should_ensemble
        from ibreeze.routing.health import load_health_ledger
        from ibreeze.routing.outcomes import load_local_calibrations

        self._turn_index += 1
        decision_id = str(uuid4())
        operator_override = await self._resolve_override()
        anchor_for_context = next(
            (candidate for candidate in self._candidates if str(candidate.get("candidate_id")) == self._anchor_candidate_id),
            self._candidates[0],
        )
        context_window = max(1, int(anchor_for_context.get("context_window", 8192)))
        context = build_routing_context(
            run_id=self._run_id,
            turn_index=self._turn_index,
            route_decision_id=decision_id,
            messages=messages,
            context_window_tokens=context_window,
            run_purpose=self._run_purpose,
            artifact_type=self._artifact_type,
            required_capability_tags=self._required_capability_tags,
            attachment_types=self._attachment_types,
            tool_count=len(tool_names),
            prior_tool_failures=self._prior_tool_failures,
            provider_failures=self._provider_failures,
            verification_failures=self._verification_failures,
            open_blocker_high_count=self._open_blocker_high_count,
            previous_tier=self._previous_tier,
            previous_confidence=self._previous_confidence,
            operator_forced_mode=operator_override,
            input_origin=self._input_origin,
        )
        self._last_context = context
        tier_decision = RulesV1Classifier().classify(context)
        # Resolve mode before capability filtering.  A fixed rollout is a
        # compatibility path: it still checks hard capabilities, but must not
        # let a C2/C3 classification disqualify the configured Anchor.
        requested_mode = self._mode_for_override(operator_override)
        rollout = startup_config()
        effective_mode = rollout.effective_mode(requested_mode, input_origin=self._input_origin)
        observe_rollout = rollout.stage in {"observe", "shadow"} and self._input_origin == "production"
        tier = _effective_route_tier(effective_mode, tier_decision.required_tier)
        self._active_tier = tier
        self._previous_tier = tier
        self._previous_confidence = tier_decision.confidence
        try:
            local_calibrations = await load_local_calibrations(
                self._read_pool,
                company_id=self._company_id,
                purpose=self._run_purpose,
                candidate_priors={
                    str(candidate.get("candidate_id")): Decimal(str(candidate.get("quality_prior", "0.5000")))
                    for candidate in self._candidates
                },
            )
        except Exception:
            # Historical outcome data is an optimisation input. A read error
            # must not prevent the immutable Snapshot from executing; score
            # with catalog priors and let the next turn retry the read.
            logger.warning("failed to load local routing calibration for run %s", self._run_id)
            local_calibrations = {str(candidate.get("candidate_id")): Decimal("0") for candidate in self._candidates}
        try:
            # Health is a hard safety gate, unlike local calibration.  A
            # persisted bench or credential-invalid state must survive
            # transport recreation and cannot be bypassed by starting a new
            # Run/turn; an unreadable ledger therefore fails closed.
            self._health.update(await load_health_ledger(self._read_pool, self._company_id, self._candidates))
        except Exception as exc:
            logger.exception("failed to load deployment health for run %s", self._run_id)
            raise RuntimeError("ROUTING_HEALTH_UNAVAILABLE") from exc
        eligible: list[tuple[Decimal, dict[str, Any]]] = []
        for candidate_item in self._candidates:
            if not self._health.get(str(candidate_item.get("candidate_id")), HealthState()).is_eligible():
                continue
            if not candidate_item.get("routing_enabled", True) and not (
                effective_mode == RoutingMode.FIXED.value
                and str(candidate_item.get("candidate_id")) == (self._anchor_candidate_id or str(self._candidates[0].get("candidate_id")))
            ):
                continue
            if int(candidate_item.get("routing_tier", 0)) < int(tier[1:]):
                continue
            if context.tool_count and not candidate_item.get("supports_tools", False):
                continue
            if context.attachment_types and not candidate_item.get("supports_vision", False):
                continue
            if not candidate_item.get("supports_streaming", False):
                continue
            if context.estimated_input_tokens + int(candidate_item.get("max_output_tokens", 0)) > int(
                candidate_item.get("context_window", 0)
            ):
                continue
            if _reasoning_level_for_candidate(candidate_item, tier) == "__unavailable__":
                continue
            calibration = local_calibrations.get(str(candidate_item.get("candidate_id")), Decimal("0"))
            try:
                catalog_quality = Decimal(str(candidate_item.get("quality_prior", "0.5000")))
            except Exception:
                catalog_quality = Decimal("0.5000")
            effective_quality = min(Decimal("1"), max(Decimal("0"), catalog_quality + calibration))
            routed_candidate = dict(candidate_item)
            # Keep the effective value in the in-memory routing projection so
            # exact score ties use the same local calibration as the score.
            # It is never persisted into the immutable Snapshot.
            routed_candidate["_effective_quality"] = str(effective_quality)
            score = score_candidate(
                routed_candidate,
                required_tier=tier,
                context=context,
                health=self._health.get(str(candidate_item.get("candidate_id")), HealthState()),
                calibration=calibration,
            )
            eligible.append((score, routed_candidate))
        ranked = [(score, candidate) for score, candidate in eligible if "single" in candidate.get("eligible_roles", ())]
        ranked_fallback = [(score, candidate) for score, candidate in eligible if "fallback" in candidate.get("eligible_roles", ())]
        ranked_proposer = [(score, candidate) for score, candidate in eligible if "proposer" in candidate.get("eligible_roles", ())]
        ranked_aggregator = [(score, candidate) for score, candidate in eligible if "aggregator" in candidate.get("eligible_roles", ())]
        ranked.sort(key=_stable_score_key)
        ranked_fallback.sort(key=_stable_score_key)
        ranked_proposer.sort(key=_stable_score_key)
        ranked_aggregator.sort(key=_stable_score_key)
        rollout_suggestion: dict[str, object] | None = None
        if observe_rollout and requested_mode != RoutingMode.FIXED.value:
            required = int(tier_decision.required_tier[1:])
            suggested = []
            for _score, suggestion_candidate in eligible:
                if not suggestion_candidate.get("routing_enabled", False) or "single" not in suggestion_candidate.get("eligible_roles", ()):
                    continue
                if int(suggestion_candidate.get("routing_tier", 0)) < required:
                    continue
                if context.tool_count and not suggestion_candidate.get("supports_tools", False):
                    continue
                if context.attachment_types and not suggestion_candidate.get("supports_vision", False):
                    continue
                if _reasoning_level_for_candidate(suggestion_candidate, tier_decision.required_tier) == "__unavailable__":
                    continue
                suggested.append(
                    (
                        score_candidate(
                            suggestion_candidate,
                            required_tier=tier_decision.required_tier,
                            context=context,
                            health=self._health.get(str(suggestion_candidate.get("candidate_id")), HealthState()),
                        ),
                        suggestion_candidate,
                    )
                )
            suggested.sort(key=_stable_score_key)
            rollout_suggestion = {
                "stage": rollout.stage,
                "suggested_mode": requested_mode,
                "suggested_tier": tier_decision.required_tier,
                "suggested_candidate_id": (str(suggested[0][1].get("candidate_id")) if suggested else None),
            }
        router_anchor_fallback = False
        if not ranked:
            # A routing failure must fall back to the configured Anchor only
            # after the same hard capability/health gate has accepted it.  A
            # fixed run may additionally use its explicitly ordered fallback
            # chain when the Anchor itself is unavailable.  Never invent a
            # candidate from the global catalog at this boundary.
            anchor_item = next(
                (
                    item
                    for item in eligible
                    if str(item[1].get("candidate_id")) == self._anchor_candidate_id
                    and "single" in item[1].get("eligible_roles", ())
                ),
                None,
            )
            if anchor_item is not None:
                ranked = [anchor_item]
                router_anchor_fallback = effective_mode != RoutingMode.FIXED.value
            elif effective_mode == RoutingMode.FIXED.value:
                fixed_fallback = next(
                    (
                        item
                        for candidate_id in self._routing_policy.get("fallback_order", ())
                        for item in ranked_fallback
                        if str(item[1].get("candidate_id")) == str(candidate_id)
                    ),
                    None,
                )
                if fixed_fallback is not None:
                    ranked = [fixed_fallback]
                else:
                    raise ValueError("MODEL_CAPABILITY_UNAVAILABLE")
            else:
                raise ValueError("MODEL_CAPABILITY_UNAVAILABLE")
        force_ensemble = operator_override == "force_ensemble"
        self._active_mode = effective_mode
        ensemble_policy = self._routing_policy.get("ensemble") or {}
        max_proposers = min(4, int(ensemble_policy.get("max_proposers", 3)), len(ranked_proposer))
        proposer_lineup_for_gate = select_proposer_candidates(
            ranked_proposer,
            max_proposers=max_proposers,
            required_tier=tier,
        )
        gated_proposers = [candidate for candidate, _role in proposer_lineup_for_gate]
        ensemble_enabled = effective_mode == RoutingMode.SELECTIVE_ENSEMBLE.value and should_ensemble(
            context,
            confidence=tier_decision.confidence,
            proposer_count=len(gated_proposers),
            aggregator_available=bool(ranked_aggregator),
            max_proposers=max_proposers,
            proposer_provider_count=len({str(candidate.get("provider_release_id")) for candidate in gated_proposers}),
            vision_proposer_count=sum(bool(candidate.get("supports_vision", False)) for candidate in gated_proposers),
            aggregator_supports_vision=bool(ranked_aggregator and ranked_aggregator[0][1].get("supports_vision", False)),
            force_ensemble=force_ensemble,
            required_tier=tier,
            estimated_input_tokens=context.estimated_input_tokens,
            aggregator_context_window=(
                int(ranked_aggregator[0][1].get("context_window", 0))
                - int(ranked_aggregator[0][1].get("max_output_tokens", 0))
                if ranked_aggregator
                else None
            ),
        )
        if not ensemble_enabled:
            if effective_mode == RoutingMode.FIXED.value and self._anchor_candidate_id:
                ranked.sort(
                    key=lambda item: (
                        0 if str(item[1].get("candidate_id")) == self._anchor_candidate_id else 1,
                        -item[0],
                        str(item[1]["candidate_id"]),
                    )
                )
            if effective_mode == RoutingMode.FIXED.value:
                anchor = next(
                    (item for _score, item in ranked if str(item.get("candidate_id")) == self._anchor_candidate_id),
                    None,
                )
                if anchor is None:
                    fallback_order = tuple(str(item) for item in self._routing_policy.get("fallback_order", ()))
                    candidate: dict[str, Any] | None = None
                    for candidate_id in fallback_order:
                        for _score, fallback_item in ranked_fallback:
                            if str(fallback_item.get("candidate_id")) == candidate_id:
                                candidate = fallback_item
                                break
                        if candidate is not None:
                            break
                    if candidate is None:
                        raise ValueError("MODEL_CAPABILITY_UNAVAILABLE")
                else:
                    candidate = anchor
            else:
                candidate = ranked[0][1]
            fallback_candidates = [(candidate, "single")]
            fallback_candidates.extend((fallback, "fallback") for fallback in self._fallback_candidates(ranked_fallback, candidate))
            policy_trail = tier_decision.policy_trail
            if rollout_suggestion is not None:
                policy_trail = policy_trail + (rollout_suggestion,)
            if router_anchor_fallback:
                policy_trail = policy_trail + (
                    {"stage": "router_fallback", "reason": "ROUTER_NO_ELIGIBLE_CANDIDATE"},
                )
            await self._prepare_decision(
                decision_id,
                fallback_candidates,
                tier=tier,
                confidence=float(tier_decision.confidence),
                context=context,
                policy_trail=policy_trail,
            )
            self._last_transport = self._transport_for(candidate, route_decision_id=decision_id, route_role="single")
            sequence = 1
            last_failure_kind: ProviderFailureKind | None = None
            for retry_number in range(3):
                try:
                    result = await self._execute_candidate(
                        self._last_transport, candidate, decision_id, "single", sequence, messages, tool_names
                    )
                    self._health[str(candidate.get("candidate_id"))] = apply_success(
                        self._health.get(str(candidate.get("candidate_id")), HealthState())
                    )
                    await self._persist_health(candidate, self._health[str(candidate.get("candidate_id"))])
                    await self._transition_decision(decision_id, "executing", "succeeded")
                    return result
                except RouteExecutionSafetyError:
                    raise
                except ModelRunCancelledError:
                    await self._transition_decision(decision_id, "executing", "cancelled")
                    raise
                except ProviderRequestError as exc:
                    self._provider_failures += 1
                    kind = (
                        ProviderFailureKind(exc.kind)
                        if exc.kind in ProviderFailureKind._value2member_map_
                        else ProviderFailureKind.INVALID_RESPONSE
                    )
                    last_failure_kind = kind
                    directive = retry_directive(kind)
                    self._health[str(candidate.get("candidate_id"))] = apply_failure(
                        self._health.get(str(candidate.get("candidate_id")), HealthState()),
                        kind,
                        retry_after_seconds=(math.ceil(exc.retry_after_ms / 1000) if exc.retry_after_ms is not None else None),
                    )
                    await self._persist_health(candidate, self._health[str(candidate.get("candidate_id"))])
                    if not directive.retry_same or retry_number >= directive.max_same_retries or exc.visible_content:
                        break
                    wait_seconds = _retry_wait_seconds(kind, exc.retry_after_ms)
                    if wait_seconds:
                        if not _run_deadline_allows_wait(self._run_deadline_at, wait_seconds):
                            break
                        await asyncio.sleep(wait_seconds)
                    sequence += 1
                    self._last_transport = self._transport_for(candidate, ":retry", route_decision_id=decision_id, route_role="single")
                except Exception:
                    last_failure_kind = ProviderFailureKind.INVALID_RESPONSE
                    await self._record_provider_failure(candidate, last_failure_kind)
                    break
            fallback_sequence = sequence + 1
            for fallback in self._fallback_candidates(ranked_fallback, candidate, failure_kind=last_failure_kind):
                self._last_transport = self._transport_for(fallback, ":fallback", route_decision_id=decision_id, route_role="fallback")
                try:
                    result = await self._execute_candidate(
                        self._last_transport, fallback, decision_id, "fallback", fallback_sequence, messages, tool_names
                    )
                    self._health[str(fallback.get("candidate_id"))] = apply_success(
                        self._health.get(str(fallback.get("candidate_id")), HealthState())
                    )
                    await self._persist_health(fallback, self._health[str(fallback.get("candidate_id"))])
                    await self._transition_decision(decision_id, "executing", "succeeded")
                    return result
                except RouteExecutionSafetyError:
                    raise
                except ModelRunCancelledError:
                    await self._transition_decision(decision_id, "executing", "cancelled")
                    raise
                except ProviderRequestError as exc:
                    failure_kind = (
                        ProviderFailureKind(exc.kind)
                        if exc.kind in ProviderFailureKind._value2member_map_
                        else ProviderFailureKind.INVALID_RESPONSE
                    )
                    await self._record_provider_failure(
                        fallback,
                        failure_kind,
                        retry_after_ms=exc.retry_after_ms,
                    )
                    fallback_sequence += 1
                    continue
                except Exception:
                    await self._record_provider_failure(fallback, ProviderFailureKind.INVALID_RESPONSE)
                    fallback_sequence += 1
                    continue
            await self._transition_decision(decision_id, "executing", "failed")
            raise RuntimeError("ROUTER_FALLBACK_EXHAUSTED")

        quorum = int(ensemble_policy.get("min_successful_proposers", 2))
        proposer_lineup = select_proposer_candidates(
            ranked_proposer,
            max_proposers=max_proposers,
            required_tier=tier,
        )
        proposers = [candidate for candidate, _role in proposer_lineup]
        proposer_roles = {str(candidate.get("candidate_id")): role for candidate, role in proposer_lineup}
        aggregator = ranked_aggregator[0][1] if ranked_aggregator else None
        if len(proposers) < 2 or aggregator is None:
            single = next((candidate for _score, candidate in ranked if "single" in candidate.get("eligible_roles", ())), ranked[0][1])
            single_fallbacks = self._fallback_candidates(ranked_fallback, single)
            await self._prepare_decision(
                decision_id,
                [(single, "single")] + [(fallback, "fallback") for fallback in single_fallbacks],
                tier=tier,
                confidence=float(tier_decision.confidence),
                context=context,
                policy_trail=tier_decision.policy_trail,
            )
            candidate = single
            self._last_transport = self._transport_for(candidate, route_decision_id=decision_id, route_role="single")
            single_failure_kind: ProviderFailureKind | None = None
            try:
                result = await self._execute_candidate(self._last_transport, candidate, decision_id, "single", 1, messages, tool_names)
            except RouteExecutionSafetyError:
                raise
            except ModelRunCancelledError:
                await self._transition_decision(decision_id, "executing", "cancelled")
                raise
            except ProviderRequestError as exc:
                single_failure_kind = (
                    ProviderFailureKind(exc.kind)
                    if exc.kind in ProviderFailureKind._value2member_map_
                    else ProviderFailureKind.INVALID_RESPONSE
                )
                self._provider_failures += 1
                self._health[str(candidate.get("candidate_id"))] = apply_failure(
                    self._health.get(str(candidate.get("candidate_id")), HealthState()),
                    single_failure_kind,
                    retry_after_seconds=(math.ceil(exc.retry_after_ms / 1000) if exc.retry_after_ms is not None else None),
                )
                await self._persist_health(candidate, self._health[str(candidate.get("candidate_id"))])
            except Exception:
                single_failure_kind = ProviderFailureKind.INVALID_RESPONSE
                await self._record_provider_failure(candidate, single_failure_kind)
            else:
                await self._transition_decision(decision_id, "executing", "succeeded")
                return result

            fallback_sequence = 2
            for fallback in self._fallback_candidates(
                ranked_fallback,
                candidate,
                failure_kind=single_failure_kind,
            ):
                self._last_transport = self._transport_for(
                    fallback,
                    ":single-fallback",
                    route_decision_id=decision_id,
                    route_role="fallback",
                )
                try:
                    result = await self._execute_candidate(
                        self._last_transport,
                        fallback,
                        decision_id,
                        "fallback",
                        fallback_sequence,
                        messages,
                        tool_names,
                    )
                except RouteExecutionSafetyError:
                    raise
                except ModelRunCancelledError:
                    await self._transition_decision(decision_id, "executing", "cancelled")
                    raise
                except ProviderRequestError as exc:
                    failure_kind = (
                        ProviderFailureKind(exc.kind)
                        if exc.kind in ProviderFailureKind._value2member_map_
                        else ProviderFailureKind.INVALID_RESPONSE
                    )
                    self._provider_failures += 1
                    self._health[str(fallback.get("candidate_id"))] = apply_failure(
                        self._health.get(str(fallback.get("candidate_id")), HealthState()),
                        failure_kind,
                        retry_after_seconds=(math.ceil(exc.retry_after_ms / 1000) if exc.retry_after_ms is not None else None),
                    )
                    await self._persist_health(fallback, self._health[str(fallback.get("candidate_id"))])
                    fallback_sequence += 1
                    continue
                except Exception:
                    await self._record_provider_failure(fallback, ProviderFailureKind.INVALID_RESPONSE)
                    fallback_sequence += 1
                    continue
                fallback_sequence += 1
                await self._transition_decision(decision_id, "executing", "succeeded")
                return result
            await self._transition_decision(decision_id, "executing", "failed")
            raise RuntimeError("ROUTER_FALLBACK_EXHAUSTED")
        ensemble_fallbacks = [
            (candidate, "fallback")
            for _score, candidate in ranked_fallback
            if candidate not in proposers and candidate is not aggregator and "fallback" in candidate.get("eligible_roles", ())
        ]
        ensemble_selections = [(candidate, "proposer") for candidate in proposers] + [(aggregator, "aggregator")] + ensemble_fallbacks
        if not ensemble_fallbacks:
            single_fallback = next(
                (
                    candidate
                    for _score, candidate in ranked
                    if candidate not in proposers and candidate is not aggregator and "single" in candidate.get("eligible_roles", ())
                ),
                None,
            )
            if single_fallback is not None:
                ensemble_selections.append((single_fallback, "single"))
        await self._prepare_decision(
            decision_id,
            ensemble_selections,
            tier=tier,
            confidence=float(tier_decision.confidence),
            aggregator_candidate_id=str(aggregator.get("candidate_id")),
            context=context,
            policy_trail=tier_decision.policy_trail,
        )
        proposer_timeout = max(1, int(ensemble_policy.get("proposer_timeout_seconds", 60)))
        aggregator_timeout = max(1, int(ensemble_policy.get("aggregator_timeout_seconds", 120)))
        proposer_max_retries = max(0, int(ensemble_policy.get("proposer_max_retries", 0)))
        max_attempts = proposer_max_retries + 1
        default_quorum = {2: 2, 3: 2, 4: 3}.get(min(max_proposers, 4), 2)
        if quorum < default_quorum:
            quorum = default_quorum

        async def run_proposer(index: int, candidate: dict[str, Any]) -> ModelTurn:
            deadline = asyncio.get_running_loop().time() + proposer_timeout
            for retry_number in range(max_attempts):
                remaining = max(0.1, deadline - asyncio.get_running_loop().time())
                sequence = 1 + index + retry_number * max_proposers
                transport = self._transport_for(
                    candidate,
                    f":proposer:{index}:{retry_number}",
                    route_decision_id=decision_id,
                    route_role="proposer",
                )
                try:
                    return await asyncio.wait_for(
                        self._execute_candidate(
                            transport,
                            candidate,
                            decision_id,
                            "proposer",
                            sequence,
                            messages,
                            tool_names,
                            cancel_status="timed_out",
                        ),
                        timeout=remaining,
                    )
                except ModelRunCancelledError:
                    raise
                except ProviderRequestError as exc:
                    self._provider_failures += 1
                    kind = (
                        ProviderFailureKind(exc.kind)
                        if exc.kind in ProviderFailureKind._value2member_map_
                        else ProviderFailureKind.INVALID_RESPONSE
                    )
                    self._health[str(candidate.get("candidate_id"))] = apply_failure(
                        self._health.get(str(candidate.get("candidate_id")), HealthState()),
                        kind,
                        retry_after_seconds=(math.ceil(exc.retry_after_ms / 1000) if exc.retry_after_ms is not None else None),
                    )
                    await self._persist_health(candidate, self._health[str(candidate.get("candidate_id"))])
                    directive = retry_directive(kind)
                    if (
                        retry_number >= proposer_max_retries
                        or not directive.retry_same
                        or exc.visible_content
                        or asyncio.get_running_loop().time() >= deadline
                    ):
                        raise
                    wait_seconds = _retry_wait_seconds(kind, exc.retry_after_ms)
                    if wait_seconds:
                        if not _run_deadline_allows_wait(self._run_deadline_at, wait_seconds):
                            break
                        await asyncio.sleep(wait_seconds)
            raise RuntimeError("ROUTING_PROPOSER_RETRY_EXHAUSTED")

        tasks = [asyncio.create_task(run_proposer(index, candidate)) for index, candidate in enumerate(proposers)]
        pending: set[asyncio.Task[ModelTurn]] = set(tasks)
        result_by_index: dict[int, ModelTurn | BaseException] = {}
        proposer_deadline = asyncio.get_running_loop().time() + proposer_timeout
        while pending:
            remaining = max(0.0, proposer_deadline - asyncio.get_running_loop().time())
            if remaining == 0:
                break
            done, pending = await asyncio.wait(pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                index = tasks.index(task)
                try:
                    result_by_index[index] = task.result()
                except BaseException as exc:
                    result_by_index[index] = exc
            successful = sum(isinstance(value, ModelTurn) for value in result_by_index.values())
            if successful >= min(quorum, len(proposers)):
                grace_done, pending = await asyncio.wait(pending, timeout=5.0)
                for task in grace_done:
                    index = tasks.index(task)
                    try:
                        result_by_index[index] = task.result()
                    except BaseException as exc:
                        result_by_index[index] = exc
                break
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        results: list[ModelTurn | BaseException] = [
            result_by_index.get(index, TimeoutError("ROUTING_PROPOSER_TIMEOUT")) for index in range(len(tasks))
        ]
        failed_candidate_ids = {
            str(proposers[index].get("candidate_id"))
            for index, result in enumerate(results)
            if not isinstance(result, ModelTurn)
        }
        cancelled = next((result for result in results if isinstance(result, ModelRunCancelledError)), None)
        if cancelled is not None:
            await self._transition_decision(decision_id, "executing", "cancelled")
            raise cancelled
        safety_failure = next((result for result in results if isinstance(result, RouteExecutionSafetyError)), None)
        if safety_failure is not None:
            raise safety_failure
        successful_proposals = [result for result in results if isinstance(result, ModelTurn)]
        if len(successful_proposals) < min(quorum, len(proposers)):
            quorum_fallback: dict[str, Any] | None = next(
                (
                    candidate
                    for _score, candidate in ranked_fallback
                    if str(candidate.get("candidate_id")) not in failed_candidate_ids
                    and "fallback" in candidate.get("eligible_roles", ())
                    and self._health.get(str(candidate.get("candidate_id")), HealthState()).is_eligible()
                ),
                None,
            )
            fallback_role = "fallback"
            if quorum_fallback is None:
                quorum_fallback = next(
                    (
                        candidate
                        for _score, candidate in ranked
                        if str(candidate.get("candidate_id")) not in failed_candidate_ids
                        and candidate not in proposers
                        and candidate is not aggregator
                        and "single" in candidate.get("eligible_roles", ())
                    ),
                    None,
                )
                fallback_role = "single"
            if quorum_fallback is None:
                await self._transition_decision(decision_id, "executing", "failed")
                raise RuntimeError("ROUTER_ENSEMBLE_QUORUM_NOT_MET")
            self._last_transport = self._transport_for(quorum_fallback, route_decision_id=decision_id, route_role=fallback_role)
            quorum_failure_kind: ProviderFailureKind | None = None
            try:
                result = await self._execute_candidate(
                    self._last_transport, quorum_fallback, decision_id, fallback_role, len(proposers) + 1, messages, tool_names
                )
            except RouteExecutionSafetyError:
                raise
            except ModelRunCancelledError:
                await self._transition_decision(decision_id, "executing", "cancelled")
                raise
            except ProviderRequestError as exc:
                quorum_failure_kind = (
                    ProviderFailureKind(exc.kind)
                    if exc.kind in ProviderFailureKind._value2member_map_
                    else ProviderFailureKind.INVALID_RESPONSE
                )
                self._provider_failures += 1
                self._health[str(quorum_fallback.get("candidate_id"))] = apply_failure(
                    self._health.get(str(quorum_fallback.get("candidate_id")), HealthState()),
                    quorum_failure_kind,
                    retry_after_seconds=(math.ceil(exc.retry_after_ms / 1000) if exc.retry_after_ms is not None else None),
                )
                await self._persist_health(quorum_fallback, self._health[str(quorum_fallback.get("candidate_id"))])
            except Exception:
                quorum_failure_kind = ProviderFailureKind.INVALID_RESPONSE
                await self._record_provider_failure(quorum_fallback, quorum_failure_kind)
            else:
                await self._transition_decision(decision_id, "executing", "succeeded")
                return result

            fallback_sequence = len(proposers) + 2
            for fallback in self._fallback_candidates(
                ranked_fallback,
                quorum_fallback,
                failure_kind=quorum_failure_kind,
                excluded_candidate_ids=failed_candidate_ids,
            ):
                self._last_transport = self._transport_for(
                    fallback,
                    ":quorum-fallback",
                    route_decision_id=decision_id,
                    route_role="fallback",
                )
                try:
                    result = await self._execute_candidate(
                        self._last_transport,
                        fallback,
                        decision_id,
                        "fallback",
                        fallback_sequence,
                        messages,
                        tool_names,
                    )
                except RouteExecutionSafetyError:
                    raise
                except ModelRunCancelledError:
                    await self._transition_decision(decision_id, "executing", "cancelled")
                    raise
                except ProviderRequestError as exc:
                    fallback_kind = (
                        ProviderFailureKind(exc.kind)
                        if exc.kind in ProviderFailureKind._value2member_map_
                        else ProviderFailureKind.INVALID_RESPONSE
                    )
                    self._provider_failures += 1
                    self._health[str(fallback.get("candidate_id"))] = apply_failure(
                        self._health.get(str(fallback.get("candidate_id")), HealthState()),
                        fallback_kind,
                        retry_after_seconds=(math.ceil(exc.retry_after_ms / 1000) if exc.retry_after_ms is not None else None),
                    )
                    await self._persist_health(fallback, self._health[str(fallback.get("candidate_id"))])
                    fallback_sequence += 1
                    continue
                except Exception:
                    await self._record_provider_failure(fallback, ProviderFailureKind.INVALID_RESPONSE)
                    fallback_sequence += 1
                    continue
                fallback_sequence += 1
                await self._transition_decision(decision_id, "executing", "succeeded")
                return result
            await self._transition_decision(decision_id, "executing", "failed")
            raise RuntimeError("ROUTER_FALLBACK_EXHAUSTED")
        # Keep proposer output in the same structured envelope as the standalone
        # ensemble executor.  The aggregator receives data, not an injected
        # prompt/system fragment; this prevents delimiter collisions and makes
        # truncation/role provenance auditable.
        proposal_envelopes = []
        for index, proposal_result in enumerate(results):
            if not isinstance(proposal_result, ModelTurn):
                continue
            turn = proposal_result
            content = turn.content or ""
            truncated = len(content) > 24000
            proposal_envelopes.append(
                {
                    "candidate_id": str(proposers[index].get("candidate_id", "")),
                    "role": proposer_roles.get(str(proposers[index].get("candidate_id", "")), "proposer"),
                    "content": content[:24000],
                    "suggested_tool_calls": [{"name": call.name, "arguments": call.arguments} for call in turn.tool_calls],
                    "truncated": truncated,
                }
            )
        packed = json.dumps(
            {
                "type": "ibreeze.routing.proposals.v1",
                "proposals": proposal_envelopes,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        aggregate_messages = messages + ({"role": "user", "content": packed},)
        aggregator_result: ModelTurn | None = None
        aggregator_failure: ProviderFailureKind | None = None
        failed_candidate_ids.add(str(aggregator.get("candidate_id")))
        for retry_number in range(2):
            sequence = 1 + max_proposers * max_attempts + retry_number
            self._last_transport = self._transport_for(
                aggregator,
                f":aggregator:{retry_number}",
                route_decision_id=decision_id,
                route_role="aggregator",
            )
            try:
                aggregator_result = await asyncio.wait_for(
                    self._execute_candidate(
                        self._last_transport,
                        aggregator,
                        decision_id,
                        "aggregator",
                        sequence,
                        aggregate_messages,
                        tool_names,
                        cancel_status="timed_out",
                    ),
                    timeout=aggregator_timeout,
                )
                break
            except RouteExecutionSafetyError:
                raise
            except ModelRunCancelledError:
                await self._transition_decision(decision_id, "executing", "cancelled")
                raise
            except ProviderRequestError as exc:
                kind = (
                    ProviderFailureKind(exc.kind)
                    if exc.kind in ProviderFailureKind._value2member_map_
                    else ProviderFailureKind.INVALID_RESPONSE
                )
                aggregator_failure = kind
                await self._record_provider_failure(
                    aggregator,
                    kind,
                    retry_after_ms=exc.retry_after_ms,
                )
                if retry_number == 0 and retry_directive(kind).retry_same and not exc.visible_content:
                    continue
                break
            except Exception:
                aggregator_failure = ProviderFailureKind.INVALID_RESPONSE
                await self._record_provider_failure(aggregator, aggregator_failure)
                break
        if aggregator_result is not None:
            await self._transition_decision(decision_id, "executing", "succeeded")
            return aggregator_result
        fallback_sequence = 1 + max_proposers * max_attempts + 2
        for fallback in self._fallback_candidates(
            ranked_fallback,
            aggregator,
            failure_kind=aggregator_failure,
            excluded_candidate_ids=failed_candidate_ids,
        ):
            self._last_transport = self._transport_for(
                fallback,
                ":aggregator-fallback",
                route_decision_id=decision_id,
                route_role="fallback",
            )
            try:
                result = await self._execute_candidate(
                    self._last_transport,
                    fallback,
                    decision_id,
                    "fallback",
                    fallback_sequence,
                    messages,
                    tool_names,
                )
            except RouteExecutionSafetyError:
                raise
            except ModelRunCancelledError:
                await self._transition_decision(decision_id, "executing", "cancelled")
                raise
            except ProviderRequestError as exc:
                failure_kind = (
                    ProviderFailureKind(exc.kind)
                    if exc.kind in ProviderFailureKind._value2member_map_
                    else ProviderFailureKind.INVALID_RESPONSE
                )
                await self._record_provider_failure(
                    fallback,
                    failure_kind,
                    retry_after_ms=exc.retry_after_ms,
                )
                fallback_sequence += 1
                continue
            except Exception:
                await self._record_provider_failure(fallback, ProviderFailureKind.INVALID_RESPONSE)
                fallback_sequence += 1
                continue
            await self._transition_decision(decision_id, "executing", "succeeded")
            return result
        await self._transition_decision(decision_id, "executing", "failed")
        raise RuntimeError("ROUTER_ENSEMBLE_AGGREGATOR_FAILED")

    def _ranked_first(self) -> dict[str, Any]:
        return self._candidates[0]

    async def probe(self) -> bool:
        transport = self._last_transport or self._transport_for(self._candidates[0])
        return await transport.probe()

    def normalize_usage(self, raw_usage: dict[str, Any]) -> UsageStats:
        transport = self._last_transport or self._transport_for(self._candidates[0])
        return transport.normalize_usage(raw_usage)


def _normalize_model_response(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize OpenAI/Anthropic-compatible broker output to ModelTurn."""
    if isinstance(result.get("content"), str) or isinstance(result.get("tool_calls"), list):
        return result
    choices = result.get("choices")
    if isinstance(choices, list) and choices:
        first: dict[str, Any] = choices[0] if isinstance(choices[0], dict) else {}
        raw_message = first.get("message")
        message: dict[str, Any] = cast(dict[str, Any], raw_message) if isinstance(raw_message, dict) else {}
        return {
            "content": message.get("content", first.get("text", "")) or "",
            "tool_calls": message.get("tool_calls", first.get("tool_calls", [])) or [],
            "usage": result.get("usage", {}) or {},
        }
    anthropic_content = result.get("content")
    if isinstance(anthropic_content, list):
        content_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in anthropic_content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text" and isinstance(block.get("text"), str):
                content_parts.append(block["text"])
            elif block_type == "tool_use":
                arguments = block.get("input", {})
                tool_calls.append(
                    {
                        "id": str(block.get("id", uuid4())),
                        "name": str(block.get("name", "unknown")),
                        "arguments": arguments if isinstance(arguments, dict) else {},
                    }
                )
        return {"content": "".join(content_parts), "tool_calls": tool_calls, "usage": result.get("usage", {}) or {}}
    responses_output = result.get("output")
    if isinstance(responses_output, list):
        content_parts = []
        tool_calls = []
        for item in responses_output:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "function_call":
                arguments = item.get("arguments", {})
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {"raw": arguments}
                tool_calls.append(
                    {
                        "id": str(item.get("call_id", item.get("id", uuid4()))),
                        "name": str(item.get("name", "unknown")),
                        "arguments": arguments if isinstance(arguments, dict) else {},
                    }
                )
            for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
                if isinstance(content, dict) and isinstance(content.get("text"), str):
                    content_parts.append(content["text"])
        return {"content": "".join(content_parts), "tool_calls": tool_calls, "usage": result.get("usage", {}) or {}}
    events = result.get("events")
    if isinstance(events, list):
        event_content_parts: list[str] = []
        event_tool_calls: list[dict[str, Any]] = []
        usage: dict[str, Any] = {}
        for event in events:
            if not isinstance(event, dict):
                continue
            raw_delta = event.get("delta")
            delta: dict[str, Any] = cast(dict[str, Any], raw_delta) if isinstance(raw_delta, dict) else event
            text = delta.get("content", delta.get("text", ""))
            if isinstance(text, str):
                event_content_parts.append(text)
            calls = delta.get("tool_calls")
            if isinstance(calls, list):
                for item in calls:
                    if not isinstance(item, dict):
                        continue
                    raw_function = item.get("function")
                    function: dict[str, Any] = cast(dict[str, Any], raw_function) if isinstance(raw_function, dict) else {}
                    arguments = function.get("arguments", item.get("arguments", {}))
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            arguments = {"raw": arguments}
                    event_tool_calls.append(
                        {
                            "id": str(item.get("id", uuid4())),
                            "name": function.get("name", item.get("name", "unknown")),
                            "arguments": arguments if isinstance(arguments, dict) else {},
                        }
                    )
            if isinstance(event.get("usage"), dict):
                usage = event["usage"]
        return {"content": "".join(event_content_parts), "tool_calls": event_tool_calls, "usage": usage}
    return {"content": "", "tool_calls": [], "usage": result.get("usage", {}) or {}}


def create_transport(
    credential_ref: str,
    model: str,
    run_id: str = "",
    provider_release_id: str = "",
    model_binding_id: str = "",
    provider_protocol: str = "openai_chat_completions",
    session: Any | None = None,
) -> ReverseRpcTransport:
    """Factory function to create the appropriate model transport.

    All providers now go through the Credential/Egress Broker and the
    authenticated reverse session.
    """
    return ReverseRpcTransport(
        credential_ref=credential_ref,
        model=model,
        run_id=run_id,
        provider_release_id=provider_release_id,
        model_binding_id=model_binding_id,
        provider_protocol=provider_protocol,
        session=session,
    )


def _protocol_path(protocol: str) -> str:
    return {
        "openai_responses": "/v1/responses",
        "anthropic_messages": "/v1/messages",
        "openai_chat_completions": "/v1/chat/completions",
    }[protocol]


def _build_provider_request(
    protocol: str,
    messages: tuple[dict[str, object], ...],
    tool_names: tuple[str, ...],
    *,
    reasoning_level: str | None = None,
    tools_are_suggestions: bool = False,
) -> dict[str, object]:
    tool_parameters: dict[str, dict[str, object]] = {
        "read_file": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Workspace-relative file path"},
                "offset": {"type": "integer", "minimum": 0},
                "length": {"type": "integer", "minimum": 1, "maximum": 1048576},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        "list_files": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "pattern": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
            "additionalProperties": False,
        },
        "search_text": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 256},
                "path": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    }
    tool_description = (
        "Non-executable tool suggestion schema; return a proposed call only"
        if tools_are_suggestions
        else "Runtime tool"
    )
    tools = [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": tool_description,
                "parameters": tool_parameters.get(name, {"type": "object", "properties": {}}),
            },
        }
        for name in tool_names
    ]
    if protocol == "anthropic_messages":
        system = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
        body: dict[str, object] = {
            "system": system,
            "messages": _anthropic_messages(messages),
            "max_tokens": 4096,
        }
        if tools:
            body["tools"] = [
                {
                    "name": name,
                    "description": tool_description,
                    "input_schema": tool_parameters.get(name, {"type": "object", "properties": {}}),
                }
                for name in tool_names
            ]
        if reasoning_level is not None:
            body["thinking"] = {
                "type": "enabled",
                "budget_tokens": {"low": 1024, "medium": 4096, "high": 8192}[reasoning_level],
            }
        return body
    if protocol == "openai_responses":
        body = {"input": _responses_input(messages), "store": False}
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "name": name,
                    "description": tool_description,
                    "parameters": tool_parameters.get(name, {"type": "object", "properties": {}}),
                }
                for name in tool_names
            ]
        if reasoning_level is not None:
            body["reasoning"] = {"effort": reasoning_level}
        return body
    body = {"messages": list(messages)}
    if tools:
        body["tools"] = tools
    if reasoning_level is not None:
        body["reasoning_effort"] = reasoning_level
    return body


def _anthropic_messages(messages: tuple[dict[str, object], ...]) -> list[dict[str, object]]:
    converted: list[dict[str, object]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            continue
        if role == "tool":
            content = message.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            converted.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": message.get("tool_call_id", ""),
                            "content": content,
                        }
                    ],
                }
            )
            continue
        if role == "assistant" and isinstance(message.get("tool_calls"), list):
            blocks: list[dict[str, object]] = []
            if isinstance(message.get("content"), str) and message["content"]:
                blocks.append({"type": "text", "text": message["content"]})
            for call in cast(list[object], message["tool_calls"]):
                if isinstance(call, dict):
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": call.get("id", ""),
                            "name": call.get("name", ""),
                            "input": call.get("arguments", {}),
                        }
                    )
            converted.append({"role": "assistant", "content": blocks})
            continue
        converted.append(dict(message))
    return converted


def _responses_input(messages: tuple[dict[str, object], ...]) -> list[dict[str, object] | str]:
    converted: list[dict[str, object] | str] = []
    for message in messages:
        role = message.get("role")
        if role == "tool":
            content = message.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            converted.append(
                {
                    "type": "function_call_output",
                    "call_id": message.get("tool_call_id", ""),
                    "output": content,
                }
            )
            continue
        if role == "assistant" and isinstance(message.get("tool_calls"), list):
            if isinstance(message.get("content"), str) and message["content"]:
                converted.append({"role": "assistant", "content": message["content"]})
            for call in cast(list[object], message["tool_calls"]):
                if isinstance(call, dict):
                    converted.append(
                        {
                            "type": "function_call",
                            "call_id": call.get("id", ""),
                            "name": call.get("name", ""),
                            "arguments": json.dumps(call.get("arguments", {}), ensure_ascii=False),
                        }
                    )
            continue
        converted.append(dict(message))
    return converted
