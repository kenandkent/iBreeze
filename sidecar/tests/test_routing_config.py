from __future__ import annotations

from ibreeze.routing.config import RoutingRolloutConfig, reset_startup_config_for_tests, startup_config


def test_rollout_defaults_and_invalid_value(monkeypatch) -> None:
    monkeypatch.delenv("IBREEZE_ROUTING_STAGE", raising=False)
    assert RoutingRolloutConfig.from_env().stage == "observe"
    monkeypatch.setenv("IBREEZE_ROUTING_STAGE", "not-a-stage")
    assert RoutingRolloutConfig.from_env().stage == "observe"
    monkeypatch.setenv("IBREEZE_ROUTING_STAGE", "selective_ensemble")
    config = RoutingRolloutConfig.from_env()
    assert config.allows_smart_single(input_origin="production")
    assert config.allows_ensemble(input_origin="evaluation")
    assert not config.allows_ensemble(input_origin="internal")


def test_rollout_effective_mode_enforces_observe_and_shadow_boundaries() -> None:
    assert RoutingRolloutConfig("observe").effective_mode("smart_single", input_origin="production") == "fixed"
    assert RoutingRolloutConfig("observe").effective_mode("selective_ensemble", input_origin="evaluation") == "fixed"
    assert RoutingRolloutConfig("shadow").effective_mode("selective_ensemble", input_origin="production") == "fixed"
    assert RoutingRolloutConfig("shadow").effective_mode("selective_ensemble", input_origin="evaluation") == "selective_ensemble"
    assert RoutingRolloutConfig("smart_single").effective_mode("selective_ensemble", input_origin="production") == "smart_single"
    assert RoutingRolloutConfig("shadow").effective_mode("corrupt_mode", input_origin="production") == "fixed"


def test_startup_config_does_not_change_when_environment_changes(monkeypatch) -> None:
    reset_startup_config_for_tests()
    monkeypatch.setenv("IBREEZE_ROUTING_STAGE", "smart_single")
    assert startup_config().stage == "smart_single"
    monkeypatch.setenv("IBREEZE_ROUTING_STAGE", "selective_ensemble")
    assert startup_config().stage == "smart_single"
    reset_startup_config_for_tests()


def test_force_ensemble_requires_selective_policy() -> None:
    from ibreeze.routing.rpc import policy_allows_ensemble

    assert policy_allows_ensemble('{"mode":"selective_ensemble"}')
    assert not policy_allows_ensemble('{"mode":"smart_single"}')
    assert not policy_allows_ensemble("not-json")
