from __future__ import annotations

import json

import pytest

from ibreeze.routing.candidates import resolve_candidate_bindings
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


def test_agent_cli_with_empty_raw_is_not_applicable() -> None:
    with pytest.raises(ValueError, match="ROUTING_POLICY_NOT_APPLICABLE"):
        validate_routing_policy(None, profile_type="agent_cli")


@pytest.mark.parametrize(
    "mutation, code",
    [
        (lambda p: p.update({"fallback_order": "not-a-list"}), "ROUTING_POLICY_INVALID"),
        (lambda p: p.update({"ensemble": "not-a-mapping"}), "ROUTING_POLICY_INVALID"),
        (lambda p: p.update({"mode": "bogus_mode"}), "ROUTING_POLICY_INVALID"),
        (lambda p: p.pop("mode"), "ROUTING_POLICY_INVALID"),
        (lambda p: p.update({"candidates": {}}), "ROUTING_POLICY_INVALID"),
        (lambda p: p["candidates"].append("junk"), "ROUTING_POLICY_INVALID"),
        (lambda p: p.update({"ensemble": {"max_proposers": 5, "min_successful_proposers": 2, "proposer_timeout_seconds": 30, "aggregator_timeout_seconds": 60, "proposer_max_retries": 1}}), "ROUTING_ENSEMBLE_INVALID"),
    ],
)
def test_policy_shape_and_mode_rejections(mutation, code: str) -> None:
    policy = _policy()
    mutation(policy)
    with pytest.raises(ValueError, match=code):
        validate_routing_policy(policy, profile_type="api_model")


def test_policy_duplicate_candidate_id() -> None:
    policy = _policy()
    policy["candidates"][1]["candidate_id"] = "11111111-1111-4111-8111-111111111111"
    with pytest.raises(ValueError, match="ROUTING_CANDIDATE_DUPLICATE"):
        validate_routing_policy(policy, profile_type="api_model")


def test_policy_rejects_invalid_secret_version_and_roles() -> None:
    policy = _policy()
    policy["candidates"][0]["credential_secret_version"] = 0
    with pytest.raises(ValueError, match="ROUTING_POLICY_INVALID"):
        validate_routing_policy(policy, profile_type="api_model")
    policy = _policy()
    policy["candidates"][0]["eligible_roles"] = ["single", "single"]
    with pytest.raises(ValueError, match="ROUTING_ROLE_INSUFFICIENT"):
        validate_routing_policy(policy, profile_type="api_model")


def test_policy_rejects_disabled_candidate_via_enabled_flag() -> None:
    policy = _policy()
    policy["candidates"][0]["enabled"] = False
    with pytest.raises(ValueError, match="ROUTING_CANDIDATE_DISABLED"):
        validate_routing_policy(policy, profile_type="api_model")


@pytest.mark.parametrize(
    "catalog, code",
    [
        ({}, "ROUTING_CANDIDATE_OUTSIDE_RELEASE"),
        (
            {
                "11111111-1111-4111-8111-111111111111": {
                    "provider_release_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
                    "model_binding_id": "55555555-5555-4555-8555-555555555555",
                }
            },
            "ROUTING_CANDIDATE_OUTSIDE_RELEASE",
        ),
        (
            {
                "11111111-1111-4111-8111-111111111111": {
                    "provider_release_id": "44444444-4444-4444-8444-444444444444",
                    "model_binding_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
                }
            },
            "ROUTING_CANDIDATE_OUTSIDE_RELEASE",
        ),
    ],
)
def test_policy_rejects_candidates_outside_catalog_release(catalog: dict, code: str) -> None:
    policy = _policy()
    with pytest.raises(ValueError, match=code):
        validate_routing_policy(policy, profile_type="api_model", catalog_release=catalog)


def test_policy_anchor_validation() -> None:
    policy = _policy()
    policy["candidates"].pop(0)
    with pytest.raises(ValueError, match="ROUTING_ANCHOR_MISSING"):
        validate_routing_policy(policy, profile_type="api_model")
    policy = _policy()
    policy["candidates"][0]["eligible_roles"] = ["proposer"]
    with pytest.raises(ValueError, match="ROUTING_ROLE_INSUFFICIENT"):
        validate_routing_policy(policy, profile_type="api_model")


@pytest.mark.parametrize(
    "mutation, code",
    [
        (lambda p: p.update({"fallback_order": []}), "ROUTING_FALLBACK_INVALID"),
        (
            lambda p: p.update(
                {
                    "fallback_order": [
                        "22222222-2222-4222-8222-222222222222",
                        "22222222-2222-4222-8222-222222222222",
                    ]
                }
            ),
            "ROUTING_FALLBACK_INVALID",
        ),
        (
            lambda p: p.update(
                {
                    "fallback_order": [
                        "22222222-2222-4222-8222-222222222222",
                        "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
                    ]
                }
            ),
            "ROUTING_FALLBACK_INVALID",
        ),
        (lambda p: p.update({"fallback_order": ["22222222-2222-4222-8222-222222222222"]}), "ROUTING_FALLBACK_INVALID"),
    ],
)
def test_policy_fallback_order_rejections(mutation, code: str) -> None:
    policy = _policy()
    mutation(policy)
    with pytest.raises(ValueError, match=code):
        validate_routing_policy(policy, profile_type="api_model")


def test_policy_requires_two_candidates_for_smart_modes() -> None:
    anchor = "11111111-1111-4111-8111-111111111111"
    policy = {
        "schema_version": 1,
        "mode": "smart_single",
        "anchor_candidate_id": anchor,
        "candidates": [
            {
                "candidate_id": anchor,
                "provider_release_id": "44444444-4444-4444-8444-444444444444",
                "model_binding_id": "55555555-5555-4555-8555-555555555555",
                "credential_ref": "66666666-6666-4666-8666-666666666666",
                "enabled": True,
                "eligible_roles": ["single", "fallback"],
                "routing_enabled": True,
            },
        ],
        "fallback_order": [anchor],
        "ensemble": {
            "max_proposers": 2,
            "min_successful_proposers": 2,
            "proposer_timeout_seconds": 30,
            "aggregator_timeout_seconds": 60,
            "proposer_max_retries": 1,
        },
    }
    with pytest.raises(ValueError, match="ROUTING_CANDIDATE_COUNT_INVALID"):
        validate_routing_policy(policy, profile_type="api_model")


@pytest.mark.parametrize(
    "mutation, code",
    [
        (lambda p: p["ensemble"].pop("max_proposers"), "ROUTING_POLICY_INVALID"),
        (lambda p: p["ensemble"].update({"max_proposers": 1}), "ROUTING_ENSEMBLE_INVALID"),
        (lambda p: p["ensemble"].update({"max_proposers": 5}), "ROUTING_ENSEMBLE_INVALID"),
        (lambda p: p["ensemble"].update({"min_successful_proposers": 5}), "ROUTING_ENSEMBLE_INVALID"),
        (lambda p: p["ensemble"].update({"proposer_timeout_seconds": 5}), "ROUTING_ENSEMBLE_INVALID"),
        (lambda p: p["ensemble"].update({"proposer_timeout_seconds": 301}), "ROUTING_ENSEMBLE_INVALID"),
        (lambda p: p["ensemble"].update({"aggregator_timeout_seconds": 5}), "ROUTING_ENSEMBLE_INVALID"),
        (lambda p: p["ensemble"].update({"aggregator_timeout_seconds": 481}), "ROUTING_ENSEMBLE_INVALID"),
        (lambda p: p["ensemble"].update({"proposer_max_retries": -1}), "ROUTING_ENSEMBLE_INVALID"),
        (lambda p: p["ensemble"].update({"proposer_max_retries": 3}), "ROUTING_ENSEMBLE_INVALID"),
    ],
)
def test_policy_ensemble_bounds(mutation, code: str) -> None:
    policy = _policy()
    mutation(policy)
    with pytest.raises(ValueError, match=code):
        validate_routing_policy(policy, profile_type="api_model")


def test_policy_ensemble_min_successful_below_default_quorum() -> None:
    policy = _policy()
    policy["ensemble"]["max_proposers"] = 2
    policy["ensemble"]["min_successful_proposers"] = 1
    with pytest.raises(ValueError, match="ROUTING_ENSEMBLE_INVALID"):
        validate_routing_policy(policy, profile_type="api_model")


# ---------------------------------------------------------------------------
# candidates.resolve_candidate_bindings coverage
# ---------------------------------------------------------------------------


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    async def fetchall(self):
        return self._rows


class _CatalogDb:
    def __init__(self, models, providers):
        self._models = models
        self._providers = providers

    async def execute(self, sql, _params):
        if "resource_type='model'" in sql:
            return _Cursor(self._models)
        return _Cursor(self._providers)


def _catalog_db(models, providers):
    return _CatalogDb(models, [(json.dumps(provider),) for provider in providers])


def _valid_policy(anchor: str, other: str, provider_id: str, binding: str, other_binding: str, credential: str, other_credential: str) -> dict:
    return {
        "schema_version": 1,
        "mode": "smart_single",
        "anchor_candidate_id": anchor,
        "candidates": [
            {"candidate_id": anchor, "provider_release_id": provider_id, "model_binding_id": binding, "credential_ref": credential, "enabled": True, "eligible_roles": ["single", "fallback"], "routing_enabled": True},
            {"candidate_id": other, "provider_release_id": provider_id, "model_binding_id": other_binding, "credential_ref": other_credential, "enabled": True, "eligible_roles": ["single", "fallback"], "routing_enabled": True},
        ],
        "fallback_order": [anchor, other],
        "ensemble": {"max_proposers": 2, "min_successful_proposers": 2, "proposer_timeout_seconds": 10, "aggregator_timeout_seconds": 10, "proposer_max_retries": 0},
    }


def _candidate_ids() -> tuple[str, str, str, str, str, str, str, str]:
    return (
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
        "33333333-3333-4333-8333-333333333333",
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        "44444444-4444-4444-8444-444444444444",
        "55555555-5555-4555-8555-555555555555",
        "66666666-6666-4666-8666-666666666666",
    )


@pytest.mark.asyncio
async def test_resolver_agent_cli_returns_fixed_marker() -> None:
    result, digest, mode = await resolve_candidate_bindings(
        None,
        company_id="c",
        employee_id="e",
        catalog_release_id="r",
        profile_type="agent_cli",
        runtime_binding={},
        routing_policy_json="{}",
    )
    assert result == "{}"
    assert digest == ""
    assert mode == "fixed"


@pytest.mark.asyncio
async def test_resolver_rejects_invalid_policy_json() -> None:
    with pytest.raises(ValueError, match="ROUTING_POLICY_INVALID"):
        await resolve_candidate_bindings(
            _catalog_db([], []),
            company_id="c",
            employee_id="e",
            catalog_release_id="r",
            profile_type="api_model",
            runtime_binding={},
            routing_policy_json="not-json",
        )
    with pytest.raises(ValueError, match="ROUTING_POLICY_INVALID"):
        await resolve_candidate_bindings(
            _catalog_db([], []),
            company_id="c",
            employee_id="e",
            catalog_release_id="r",
            profile_type="api_model",
            runtime_binding={},
            routing_policy_json="[]",
        )


@pytest.mark.asyncio
async def test_resolver_skips_non_dict_bindings_and_sorts() -> None:
    anchor, other, provider_id, binding_a, binding_b, cred_a, cred_b, model_a = _candidate_ids()
    model_b = "77777777-7777-4777-8777-777777777777"
    models = [
        (model_a, json.dumps({"id": model_a, "context_window": 1000, "max_output_tokens": 100, "supports_streaming": True, "routing_tier": 1, "quality_prior": "0.5000", "tool_reliability_prior": "0.5000", "latency_prior_ms": 100, "routing_enabled": True})),
        (model_b, json.dumps({"id": model_b, "context_window": 1000, "max_output_tokens": 100, "supports_streaming": True, "routing_tier": 1, "quality_prior": "0.5000", "tool_reliability_prior": "0.5000", "latency_prior_ms": 100, "routing_enabled": True})),
    ]
    provider = {
        "id": provider_id,
        "key": "provider",
        "protocol": "openai_responses",
        "model_bindings": [
            {"binding_id": binding_a, "model_id": model_a, "provider_model_name": "a", "request_defaults": {}},
            {"model_id": model_b},
            {"binding_id": binding_b, "model_id": model_b, "provider_model_name": "b", "request_defaults": {}},
        ],
    }
    policy = _valid_policy(anchor, other, provider_id, binding_a, binding_b, cred_a, cred_b)
    result, _digest, _mode = await resolve_candidate_bindings(
        _catalog_db(models, [provider]),
        company_id="c",
        employee_id="e",
        catalog_release_id="r",
        profile_type="api_model",
        runtime_binding={},
        routing_policy_json=json.dumps(policy),
    )
    snapshot = json.loads(result)
    assert [item["model_binding_id"] for item in snapshot] == [binding_a, binding_b]


@pytest.mark.asyncio
async def test_resolver_rejects_candidates_field_shape() -> None:
    anchor, other, provider_id, binding_a, binding_b, cred_a, cred_b, _model_a = _candidate_ids()
    policy = _valid_policy(anchor, other, provider_id, binding_a, binding_b, cred_a, cred_b)
    policy["candidates"] = {}
    with pytest.raises(ValueError, match="ROUTING_POLICY_INVALID"):
        await resolve_candidate_bindings(
            _catalog_db([], []),
            company_id="c",
            employee_id="e",
            catalog_release_id="r",
            profile_type="api_model",
            runtime_binding={},
            routing_policy_json=json.dumps(policy),
        )


@pytest.mark.asyncio
async def test_resolver_rejects_binding_missing_from_catalog() -> None:
    anchor, other, provider_id, binding_a, binding_b, cred_a, cred_b, model_a = _candidate_ids()
    model_b = "77777777-7777-4777-8777-777777777777"
    models = [
        (model_a, json.dumps({"id": model_a, "context_window": 1000, "max_output_tokens": 100, "supports_streaming": True, "routing_tier": 1, "quality_prior": "0.5000", "tool_reliability_prior": "0.5000", "latency_prior_ms": 100, "routing_enabled": True})),
        (model_b, json.dumps({"id": model_b, "context_window": 1000, "max_output_tokens": 100, "supports_streaming": True, "routing_tier": 1, "quality_prior": "0.5000", "tool_reliability_prior": "0.5000", "latency_prior_ms": 100, "routing_enabled": True})),
    ]
    # binding_b exists in the catalog but the policy's other candidate points
    # at a binding that no provider exposes.
    provider = {
        "id": provider_id,
        "key": "provider",
        "protocol": "openai_responses",
        "model_bindings": [
            {"binding_id": binding_a, "model_id": model_a, "provider_model_name": "a", "request_defaults": {}},
        ],
    }
    policy = _valid_policy(anchor, other, provider_id, binding_a, binding_b, cred_a, cred_b)
    with pytest.raises(ValueError, match="ROUTING_CANDIDATE_OUTSIDE_RELEASE"):
        await resolve_candidate_bindings(
            _catalog_db(models, [provider]),
            company_id="c",
            employee_id="e",
            catalog_release_id="r",
            profile_type="api_model",
            runtime_binding={},
            routing_policy_json=json.dumps(policy),
        )


@pytest.mark.asyncio
async def test_resolver_rejects_provider_id_mismatch() -> None:
    anchor, other, _provider_id, binding_a, binding_b, cred_a, cred_b, model_a = _candidate_ids()
    model_b = "77777777-7777-4777-8777-777777777777"
    models = [
        (model_a, json.dumps({"id": model_a, "context_window": 1000, "max_output_tokens": 100, "supports_streaming": True, "routing_tier": 1, "quality_prior": "0.5000", "tool_reliability_prior": "0.5000", "latency_prior_ms": 100, "routing_enabled": True})),
        (model_b, json.dumps({"id": model_b, "context_window": 1000, "max_output_tokens": 100, "supports_streaming": True, "routing_tier": 1, "quality_prior": "0.5000", "tool_reliability_prior": "0.5000", "latency_prior_ms": 100, "routing_enabled": True})),
    ]
    # Provider rows carry a different id than the policy's provider_release_id.
    provider = {
        "id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        "key": "provider",
        "protocol": "openai_responses",
        "model_bindings": [
            {"binding_id": binding_a, "model_id": model_a, "provider_model_name": "a", "request_defaults": {}},
            {"binding_id": binding_b, "model_id": model_b, "provider_model_name": "b", "request_defaults": {}},
        ],
    }
    policy = _valid_policy(anchor, other, provider["id"], binding_a, binding_b, cred_a, cred_b)
    policy["candidates"][0]["provider_release_id"] = "11111111-1111-4111-8111-111111111111"
    with pytest.raises(ValueError, match="ROUTING_CANDIDATE_OUTSIDE_RELEASE"):
        await resolve_candidate_bindings(
            _catalog_db(models, [provider]),
            company_id="c",
            employee_id="e",
            catalog_release_id="r",
            profile_type="api_model",
            runtime_binding={},
            routing_policy_json=json.dumps(policy),
        )
