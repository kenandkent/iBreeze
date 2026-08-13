from __future__ import annotations

import json
from pathlib import Path

import pytest

from ibreeze.routing.canonical_json import canonical_json
from ibreeze.routing.policy import validate_routing_policy


def _policy() -> dict[str, object]:
    anchor = "11111111-1111-4111-8111-111111111111"
    second = "22222222-2222-4222-8222-222222222222"
    aggregator = "33333333-3333-4333-8333-333333333333"
    return {
        "schema_version": 1,
        "mode": "selective_ensemble",
        "anchor_candidate_id": anchor,
        "candidates": [
            {
                "candidate_id": anchor,
                "provider_release_id": "44444444-4444-4444-8444-444444444444",
                "model_binding_id": "55555555-5555-4555-8555-555555555555",
                "credential_ref": "66666666-6666-4666-8666-666666666666",
                "enabled": True,
                "eligible_roles": ["single", "fallback", "proposer"],
                "routing_enabled": True,
            },
            {
                "candidate_id": second,
                "provider_release_id": "77777777-7777-4777-8777-777777777777",
                "model_binding_id": "88888888-8888-4888-8888-888888888888",
                "credential_ref": "99999999-9999-4999-8999-999999999999",
                "enabled": True,
                "eligible_roles": ["proposer", "fallback"],
                "routing_enabled": True,
            },
            {
                "candidate_id": aggregator,
                "provider_release_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "model_binding_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                "credential_ref": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                "enabled": True,
                "eligible_roles": ["aggregator", "fallback"],
                "routing_enabled": True,
            },
        ],
        "fallback_order": [second, anchor],
        "ensemble": {
            "max_proposers": 2,
            "min_successful_proposers": 2,
            "proposer_timeout_seconds": 30,
            "aggregator_timeout_seconds": 60,
            "proposer_max_retries": 1,
        },
    }


def test_policy_is_canonical_and_hashable() -> None:
    result = validate_routing_policy(_policy(), profile_type="api_model")
    assert result.mode.value == "selective_ensemble"
    assert result.canonical_json.index('"anchor_candidate_id"') < result.canonical_json.index('"candidates"')
    assert len(result.sha256) == 64


@pytest.mark.parametrize(
    "mutation, code",
    [
        (lambda p: p["candidates"][1].update({"routing_enabled": False}), "ROUTING_CANDIDATE_DISABLED"),
        (lambda p: p.update({"fallback_order": ["b", "b"]}), "ROUTING_FALLBACK_INVALID"),
        (lambda p: p["candidates"].pop(), "ROUTING_ROLE_INSUFFICIENT"),
    ],
)
def test_policy_rejects_invalid_candidate_configuration(mutation, code: str) -> None:
    policy = _policy()
    mutation(policy)
    with pytest.raises(ValueError, match=code):
        validate_routing_policy(policy, profile_type="api_model")


def test_agent_cli_policy_is_forbidden() -> None:
    with pytest.raises(ValueError, match="ROUTING_POLICY_FORBIDDEN"):
        validate_routing_policy(_policy(), profile_type="agent_cli")


def test_api_model_policy_is_required() -> None:
    with pytest.raises(ValueError, match="ROUTING_POLICY_REQUIRED"):
        validate_routing_policy(None, profile_type="api_model")


def test_policy_requires_uuid_identity_fields() -> None:
    policy = _policy()
    policy["candidates"][0]["candidate_id"] = "not-a-uuid"
    with pytest.raises(ValueError, match="ROUTING_POLICY_INVALID"):
        validate_routing_policy(policy, profile_type="api_model")


def test_canonical_fixture_preserves_nested_unicode_and_integer_values() -> None:
    fixture_path = Path(__file__).parents[2] / "packages/contracts/fixtures/routing-canonical-json.v1.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    canonical = canonical_json(fixture)
    assert '"metadata":{"integer":0' in canonical
    assert "\\n" in canonical
    assert "." not in canonical.split('"integer":0', 1)[1].split(",", 1)[0]
