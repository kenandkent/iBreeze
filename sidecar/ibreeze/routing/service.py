"""Transactional routing lifecycle orchestration.

The service owns the ordering guarantee shared by the runtime and repository:
Decision is durable before an Attempt, and an Attempt is terminal before a
ModelTurn is returned to the Agent Loop.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from ibreeze.routing.classifier import RulesV1Classifier
from ibreeze.routing.context import RoutingContext
from ibreeze.routing.engine import RoutePlan, RoutingPolicyEngine
from ibreeze.routing.repository import RoutingRepository
from ibreeze.routing.types import ProviderFailureKind, RouteRole


@dataclass(frozen=True, slots=True)
class AttemptResult:
    status: str
    response: Any | None = None
    failure_kind: ProviderFailureKind | None = None
    http_status: int | None = None
    request_id: str | None = None


class RoutingService:
    def __init__(self, repository: RoutingRepository | None = None) -> None:
        self.repository = repository or RoutingRepository()
        self.classifier = RulesV1Classifier()
        self.engine = RoutingPolicyEngine()

    async def plan_and_persist(
        self,
        db: Any,
        *,
        context: RoutingContext,
        candidates: tuple[dict[str, Any], ...],
        policy: Any,
        health: dict[Any, Any] | None = None,
    ) -> tuple[str, RoutePlan]:
        tier = self.classifier.classify(context)
        plan = self.engine.plan(context, tier, candidates, health or {}, policy)
        decision_id = context.route_decision_id or str(uuid4())
        selections = [{"candidate_id": str(item.candidate.get("candidate_id")), "role": item.role.value} for item in plan.selected]
        selections.extend({"candidate_id": str(item.candidate.get("candidate_id")), "role": item.role.value} for item in plan.fallback)
        if plan.aggregator is not None:
            selections.append({"candidate_id": str(plan.aggregator.candidate.get("candidate_id")), "role": plan.aggregator.role.value})
        await self.repository.create_decision(
            db,
            decision_id=decision_id,
            company_id=str(candidates[0].get("company_id", "")),
            run_id=context.run_id,
            turn_index=context.turn_index,
            execution_snapshot_id=str(candidates[0].get("execution_snapshot_id", "")),
            routing_mode=plan.mode,
            classifier_version=self.classifier.version,
            input_fingerprint=context.fingerprint(),
            required_tier=plan.required_tier,
            confidence=float(plan.confidence),
            selected_kind=plan.selected_kind,
            selected_bindings=selections,
            policy_trail=list(plan.policy_trail),
            aggregator_candidate_id=str(plan.aggregator.candidate.get("candidate_id")) if plan.aggregator else None,
        )
        return decision_id, plan

    async def execute_attempt(
        self,
        db: Any,
        *,
        decision_id: str,
        candidate: dict[str, Any],
        role: RouteRole,
        sequence: int,
        request: Callable[..., Awaitable[AttemptResult]],
    ) -> AttemptResult:
        """Execute one physical Attempt with an auditable CAS lifecycle.

        New request adapters receive ``(attempt_id, on_accepted,
        on_streaming)`` and invoke the callbacks immediately after the Rust
        Broker acknowledges the request and emits its first stream event.  A
        one-argument callback remains supported for legacy fixed callers; in
        that path the terminal result is persisted conservatively after the
        request returns.  The production API Model path uses
        ``RoutedModelTransport`` and the callback form.
        """
        attempt_id = str(uuid4())
        credential_ref = str(candidate.get("credential_ref", ""))
        credential_hash = hashlib.sha256(credential_ref.encode("utf-8")).hexdigest()
        await self.repository.create_attempt(
            db,
            attempt_id=attempt_id,
            route_decision_id=decision_id,
            company_id=str(candidate.get("company_id", "")),
            run_id=str(candidate.get("run_id", "")),
            execution_snapshot_id=str(candidate.get("execution_snapshot_id", "")),
            attempt_sequence=sequence,
            role=role,
            candidate_id=str(candidate["candidate_id"]),
            provider_release_id=str(candidate["provider_release_id"]),
            model_binding_id=str(candidate["model_binding_id"]),
            credential_ref_sha256=credential_hash,
            request_id=None,
        )
        accepted_emitted = False
        streaming_emitted = False

        async def on_accepted(request_id: str) -> None:
            nonlocal accepted_emitted
            if accepted_emitted:
                return
            if request_id:
                await self.repository.bind_attempt_request(db, attempt_id=attempt_id, request_id=request_id)
            await self.repository.transition_attempt(db, attempt_id, "created", "accepted")
            accepted_emitted = True

        async def on_streaming() -> None:
            nonlocal streaming_emitted
            if streaming_emitted:
                return
            # A provider may emit the first event before a delayed accepted
            # callback reaches the Sidecar; close that gap deterministically.
            if not accepted_emitted:
                await on_accepted("")
            await self.repository.transition_attempt(db, attempt_id, "accepted", "streaming")
            streaming_emitted = True

        cancelled = False
        try:
            parameters = inspect.signature(request).parameters
            accepts_callbacks = len(parameters) >= 3 or any(
                parameter.kind is inspect.Parameter.VAR_POSITIONAL or parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            )
            if accepts_callbacks:
                result = await request(attempt_id, on_accepted, on_streaming)
            else:
                result = await request(attempt_id)
        except asyncio.CancelledError:
            result = AttemptResult(status="cancelled")
            cancelled = True
        except TimeoutError:
            result = AttemptResult(status="timed_out", failure_kind=ProviderFailureKind.TIMEOUT)
        except Exception as exc:
            failure_kind = getattr(exc, "kind", ProviderFailureKind.INVALID_RESPONSE)
            try:
                normalized_kind = ProviderFailureKind(str(failure_kind))
            except ValueError:
                normalized_kind = ProviderFailureKind.INVALID_RESPONSE
            result = AttemptResult(status="failed", failure_kind=normalized_kind, http_status=getattr(exc, "http_status", None))
        if result.request_id and not accepted_emitted:
            await on_accepted(result.request_id)
        if result.status == "succeeded" and not streaming_emitted:
            await on_streaming()
        terminal = (
            "succeeded"
            if result.status == "succeeded"
            else "timed_out"
            if result.status == "timed_out"
            else "cancelled"
            if result.status == "cancelled"
            else "failed"
        )
        for expected_status in ("streaming", "accepted", "created"):
            if await self.repository.transition_attempt(
                db,
                attempt_id,
                expected_status,
                terminal,
                failure_kind=result.failure_kind,
                http_status=result.http_status,
            ):
                break
        if cancelled:
            raise asyncio.CancelledError
        return result
