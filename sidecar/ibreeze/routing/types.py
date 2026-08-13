from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RoutingMode(StrEnum):
    FIXED = "fixed"
    SMART_SINGLE = "smart_single"
    SELECTIVE_ENSEMBLE = "selective_ensemble"


class RouteRole(StrEnum):
    SINGLE = "single"
    PROPOSER = "proposer"
    AGGREGATOR = "aggregator"
    FALLBACK = "fallback"


class ProviderFailureKind(StrEnum):
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_OVERLOADED = "PROVIDER_OVERLOADED"
    TRANSPORT_TRANSIENT = "TRANSPORT_TRANSIENT"
    TIMEOUT = "TIMEOUT"
    CONTEXT_OVERFLOW = "CONTEXT_OVERFLOW"
    AUTH_INVALID = "AUTH_INVALID"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    INSUFFICIENT_CREDITS = "INSUFFICIENT_CREDITS"
    BAD_REQUEST = "BAD_REQUEST"
    POLICY_REFUSAL = "POLICY_REFUSAL"
    INVALID_RESPONSE = "INVALID_RESPONSE"


@dataclass(frozen=True, slots=True)
class DeploymentKey:
    company_id: str
    provider_release_id: str
    model_binding_id: str
    credential_ref: str

    @property
    def credential_ref_sha256(self) -> str:
        import hashlib

        return hashlib.sha256(self.credential_ref.encode("utf-8")).hexdigest()
