from __future__ import annotations

import json

import pytest

from ibreeze.routing.candidates import resolve_candidate_bindings


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


@pytest.mark.asyncio
async def test_candidate_resolver_sorts_snapshot_by_binding_then_candidate() -> None:
    candidate_a = "11111111-1111-4111-8111-111111111111"
    candidate_b = "22222222-2222-4222-8222-222222222222"
    provider_id = "33333333-3333-4333-8333-333333333333"
    binding_a = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    binding_b = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    credential_a = "44444444-4444-4444-8444-444444444444"
    credential_b = "55555555-5555-4555-8555-555555555555"
    model_a = "66666666-6666-4666-8666-666666666666"
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
            {"binding_id": binding_b, "model_id": model_b, "provider_model_name": "b", "request_defaults": {}},
            {"binding_id": binding_a, "model_id": model_a, "provider_model_name": "a", "request_defaults": {}},
        ],
    }
    policy = {
        "schema_version": 1,
        "mode": "smart_single",
        "anchor_candidate_id": candidate_b,
        "candidates": [
            {"candidate_id": candidate_b, "provider_release_id": provider_id, "model_binding_id": binding_b, "credential_ref": credential_b, "enabled": True, "eligible_roles": ["single", "fallback"], "routing_enabled": True},
            {"candidate_id": candidate_a, "provider_release_id": provider_id, "model_binding_id": binding_a, "credential_ref": credential_a, "enabled": True, "eligible_roles": ["single", "fallback"], "routing_enabled": True},
        ],
        "fallback_order": [candidate_b, candidate_a],
        "ensemble": {"max_proposers": 2, "min_successful_proposers": 2, "proposer_timeout_seconds": 10, "aggregator_timeout_seconds": 10, "proposer_max_retries": 0},
    }

    result, _hash, _mode = await resolve_candidate_bindings(
        _CatalogDb(models, [(json.dumps(provider),)]),
        company_id="88888888-8888-4888-8888-888888888888",
        employee_id="99999999-9999-4999-8999-999999999999",
        catalog_release_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        profile_type="api_model",
        runtime_binding={},
        routing_policy_json=json.dumps(policy),
    )
    snapshot = json.loads(result)
    assert [item["model_binding_id"] for item in snapshot] == [binding_a, binding_b]
