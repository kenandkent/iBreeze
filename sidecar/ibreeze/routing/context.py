"""Deterministic, privacy-preserving routing context construction."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

_CODE_LINE = re.compile(
    r"^\s*(def|class|fn|function|import|from|const|let|var|SELECT|INSERT|UPDATE|CREATE)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class RoutingContext:
    route_decision_id: str
    run_id: str
    turn_index: int
    run_purpose: str
    artifact_type: str | None
    required_capability_tags: tuple[str, ...]
    message_char_count: int
    estimated_input_tokens: int
    context_window_tokens: int
    context_pressure: float
    contains_code: bool
    contains_structured_schema: bool
    attachment_types: tuple[str, ...]
    tool_count: int
    prior_tool_failures: int = 0
    provider_failures: int = 0
    verification_failures: int = 0
    open_blocker_high_count: int = 0
    previous_tier: str | None = None
    previous_confidence: float | None = None
    operator_forced_mode: str | None = None
    input_origin: str = "production"
    token_estimator: str = "fallback_bytes_v1"
    contains_review_signal: bool = False

    def fingerprint(self) -> str:
        features = {
            "message_char_count": self.message_char_count,
            "estimated_input_tokens": self.estimated_input_tokens,
            "context_window_tokens": self.context_window_tokens,
            "context_pressure": round(self.context_pressure, 8),
            "artifact_type": self.artifact_type,
            "required_capability_tags": list(self.required_capability_tags),
            "contains_code": self.contains_code,
            "contains_structured_schema": self.contains_structured_schema,
            "attachment_types": list(self.attachment_types),
            "tool_count": self.tool_count,
            "prior_tool_failures": self.prior_tool_failures,
            "provider_failures": self.provider_failures,
            "verification_failures": self.verification_failures,
            "open_blocker_high_count": self.open_blocker_high_count,
            "previous_tier": self.previous_tier,
            "previous_confidence": self.previous_confidence,
            "operator_forced_mode": self.operator_forced_mode,
            "input_origin": self.input_origin,
            "run_purpose": self.run_purpose,
            "token_estimator": self.token_estimator,
            "contains_review_signal": self.contains_review_signal,
        }
        payload = f"{self.run_id}:{self.turn_index}:" + json.dumps(features, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _estimate_tokens(text: str, *, tokenizer: object | None) -> tuple[int, str]:
    if tokenizer is not None and callable(tokenizer):
        value = tokenizer(text)
        if isinstance(value, int) and value >= 0:
            return value, "catalog_tokenizer"
    return max(1, math.ceil(len(text.encode("utf-8")) / 4)), "fallback_bytes_v1"


def _contains_code(text: str) -> bool:
    if "```" in text:
        return True
    return sum(1 for line in text.splitlines() if _CODE_LINE.search(line)) >= 2


def _contains_schema(text: str) -> bool:
    lowered = text.lower()
    return bool(
        ("$schema" in text and "properties" in text)
        or ("openapi" in lowered and "paths" in lowered)
        or any(marker in text for marker in ("严格 JSON", "固定字段", "不得增加字段"))
    )


def _contains_review_signal(text: str) -> bool:
    return bool(re.search(r"分析|review|审查|检查|验证|verify|test", text, re.IGNORECASE))


def build_routing_context(
    *,
    run_id: str,
    turn_index: int,
    messages: Iterable[dict[str, object]],
    context_window_tokens: int,
    run_purpose: str = "task_execution",
    route_decision_id: str = "",
    artifact_type: str | None = None,
    required_capability_tags: Iterable[str] = (),
    attachment_types: Iterable[str] = (),
    tool_count: int = 0,
    prior_tool_failures: int = 0,
    provider_failures: int = 0,
    verification_failures: int = 0,
    open_blocker_high_count: int = 0,
    previous_tier: str | None = None,
    previous_confidence: float | None = None,
    operator_forced_mode: str | None = None,
    input_origin: str = "production",
    tokenizer: object | None = None,
) -> RoutingContext:
    if input_origin not in {"production", "evaluation"}:
        raise ValueError("ROUTING_INPUT_ORIGIN_INVALID")
    if input_origin == "production" and operator_forced_mode == "evaluation":
        raise ValueError("ROUTING_INPUT_ORIGIN_INVALID")
    normalized_parts: list[str] = []
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            normalized_parts.append(unicodedata.normalize("NFKC", content))
    text = "\n".join(normalized_parts)
    estimate, estimator = _estimate_tokens(text, tokenizer=tokenizer)
    window = max(1, int(context_window_tokens))
    return RoutingContext(
        route_decision_id=route_decision_id,
        run_id=run_id,
        turn_index=int(turn_index),
        run_purpose=run_purpose,
        artifact_type=artifact_type,
        required_capability_tags=tuple(sorted(set(str(item) for item in required_capability_tags))),
        message_char_count=len(text),
        estimated_input_tokens=estimate,
        context_window_tokens=window,
        context_pressure=min(1.0, max(0.0, estimate / window)),
        contains_code=_contains_code(text),
        contains_structured_schema=_contains_schema(text),
        attachment_types=tuple(sorted(set(str(item) for item in attachment_types))),
        tool_count=max(0, int(tool_count)),
        prior_tool_failures=max(0, int(prior_tool_failures)),
        provider_failures=max(0, int(provider_failures)),
        verification_failures=max(0, int(verification_failures)),
        open_blocker_high_count=max(0, int(open_blocker_high_count)),
        previous_tier=previous_tier,
        previous_confidence=previous_confidence,
        operator_forced_mode=operator_forced_mode,
        input_origin=input_origin,
        token_estimator=estimator,
        contains_review_signal=_contains_review_signal(text),
    )
