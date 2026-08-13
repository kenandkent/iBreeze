"""Process-scoped routing rollout configuration."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)
_STAGES = {"observe", "shadow", "smart_single", "selective_ensemble", "learning_candidate"}
_STARTUP_CONFIG: RoutingRolloutConfig | None = None


@dataclass(frozen=True, slots=True)
class RoutingRolloutConfig:
    stage: str = "observe"

    @classmethod
    def from_env(cls) -> RoutingRolloutConfig:
        raw = os.getenv("IBREEZE_ROUTING_STAGE")
        if raw is None or raw == "":
            return cls("observe")
        if raw not in _STAGES:
            logger.error("invalid IBREEZE_ROUTING_STAGE; using observe")
            return cls("observe")
        return cls(raw)

    def allows_smart_single(self, *, input_origin: str) -> bool:
        return self.stage in {"smart_single", "selective_ensemble", "learning_candidate"} and input_origin == "production"

    def allows_ensemble(self, *, input_origin: str) -> bool:
        return self.stage in {"selective_ensemble", "learning_candidate"} and input_origin in {"production", "evaluation"}

    def effective_mode(self, requested_mode: str, *, input_origin: str) -> str:
        """Resolve the process rollout stage without allowing public shadow calls."""
        if input_origin not in {"production", "evaluation"}:
            raise ValueError("ROUTING_INPUT_ORIGIN_INVALID")
        if requested_mode not in {"fixed", "smart_single", "selective_ensemble"}:
            return "fixed"
        if self.stage == "observe":
            return "fixed"
        if self.stage == "shadow":
            return requested_mode if input_origin == "evaluation" else "fixed"
        if requested_mode == "selective_ensemble" and not self.allows_ensemble(input_origin=input_origin):
            return "smart_single"
        if requested_mode == "smart_single" and not self.allows_smart_single(input_origin=input_origin):
            return "fixed"
        return requested_mode


def startup_config() -> RoutingRolloutConfig:
    """Return the process-start routing stage snapshot.

    The stage is deployment configuration, not request data. It is therefore
    intentionally read once and remains unchanged until the Sidecar restarts.
    """
    global _STARTUP_CONFIG
    if _STARTUP_CONFIG is None:
        _STARTUP_CONFIG = RoutingRolloutConfig.from_env()
    return _STARTUP_CONFIG


def reset_startup_config_for_tests() -> None:
    """Reset the process snapshot for isolated unit tests only."""
    global _STARTUP_CONFIG
    _STARTUP_CONFIG = None
