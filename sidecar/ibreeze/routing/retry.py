"""Stable retry/fallback directives for the twelve provider failure kinds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ibreeze.routing.types import ProviderFailureKind


@dataclass(frozen=True, slots=True)
class RetryDirective:
    retry_same: bool
    max_same_retries: int
    fallback_allowed: bool
    fallback_constraint: Literal["any", "larger_context", "different_credential_or_provider", "none"]
    bench_immediately: bool
    health_strike: bool


_DIRECTIVES: dict[ProviderFailureKind, RetryDirective] = {
    ProviderFailureKind.RATE_LIMITED: RetryDirective(True, 1, True, "any", True, True),
    ProviderFailureKind.PROVIDER_OVERLOADED: RetryDirective(True, 1, True, "any", False, True),
    ProviderFailureKind.TRANSPORT_TRANSIENT: RetryDirective(True, 2, True, "any", False, True),
    ProviderFailureKind.TIMEOUT: RetryDirective(True, 1, True, "any", False, True),
    ProviderFailureKind.CONTEXT_OVERFLOW: RetryDirective(False, 0, True, "larger_context", False, False),
    ProviderFailureKind.AUTH_INVALID: RetryDirective(False, 0, True, "different_credential_or_provider", False, False),
    ProviderFailureKind.MODEL_NOT_FOUND: RetryDirective(False, 0, True, "any", True, True),
    ProviderFailureKind.UNSUPPORTED_CAPABILITY: RetryDirective(False, 0, True, "any", True, True),
    ProviderFailureKind.INSUFFICIENT_CREDITS: RetryDirective(False, 0, True, "different_credential_or_provider", True, True),
    ProviderFailureKind.BAD_REQUEST: RetryDirective(False, 0, False, "none", False, False),
    ProviderFailureKind.POLICY_REFUSAL: RetryDirective(False, 0, False, "none", False, False),
    ProviderFailureKind.INVALID_RESPONSE: RetryDirective(True, 1, True, "any", False, True),
}


def retry_directive(kind: ProviderFailureKind | str) -> RetryDirective:
    value = kind if isinstance(kind, ProviderFailureKind) else ProviderFailureKind(str(kind))
    return _DIRECTIVES[value]
