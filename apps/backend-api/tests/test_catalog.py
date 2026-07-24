"""G.6/G.13 canonical catalog contract tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.catalog.models import AgentCatalog


def _headers(tokens: dict[str, object], **extra: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        **extra,
    }


def _agent_body(key: str = "codex_cli") -> dict[str, object]:
    return {
        "key": key,
        "display_name": "Codex CLI",
        "description": "Codex command-line Agent adapter.",
    }


def _agent_version() -> dict[str, object]:
    return {
        "min_version": "1.0.0",
        "max_version_exclusive": "2.0.0",
        "executable_names": ["codex"],
        "supported_platforms": ["macos_arm64"],
        "probe_argv": ["codex", "--version"],
        "capability_tags": ["code", "review"],
        "network_domains": ["api.openai.com"],
        "adapter_contract_version": 1,
    }


def _model_body(model_key: str = "gpt-5") -> dict[str, object]:
    return {
        "provider_key": "openai",
        "model_key": model_key,
        "display_name": "GPT-5",
        "context_window": 32_000,
        "max_output_tokens": 8_000,
        "tokenizer_key": "o200k_base",
        "supports_tools": True,
        "supports_streaming": True,
        "supports_vision": True,
    }


def _provider_body(key: str = "openai") -> dict[str, object]:
    return {
        "key": key,
        "display_name": "OpenAI",
        "protocol": "openai_responses",
        "base_url": "https://api.openai.com/v1/",
        "auth_scheme": "bearer",
    }


@pytest.mark.asyncio
async def test_agent_revision_lifecycle_and_optimistic_lock(
    client: AsyncClient,
    admin_tokens: dict[str, object],
) -> None:
    created = await client.post(
        "/admin/api/v1/agents",
        json=_agent_body(),
        headers=_headers(admin_tokens),
    )
    assert created.status_code == 201, created.text
    agent = created.json()
    assert agent["catalog_revision"] == 1
    assert agent["status"] == "draft"
    assert agent["version"] == 1

    missing_match = await client.patch(
        f"/admin/api/v1/agents/{agent['id']}",
        json={"display_name": "Changed"},
        headers=_headers(admin_tokens),
    )
    assert missing_match.status_code == 428

    updated = await client.patch(
        f"/admin/api/v1/agents/{agent['id']}",
        json={"display_name": "Changed"},
        headers=_headers(admin_tokens, **{"If-Match": "1"}),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2
    conflict = await client.patch(
        f"/admin/api/v1/agents/{agent['id']}",
        json={"display_name": "Stale"},
        headers=_headers(admin_tokens, **{"If-Match": "1"}),
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "OPTIMISTIC_LOCK_CONFLICT"


@pytest.mark.asyncio
async def test_agent_validation_requires_non_overlapping_semver_ranges(
    client: AsyncClient,
    admin_tokens: dict[str, object],
) -> None:
    agent = (
        await client.post(
            "/admin/api/v1/agents",
            json=_agent_body("claude_code"),
            headers=_headers(admin_tokens),
        )
    ).json()
    missing = await client.post(
        f"/admin/api/v1/agents/{agent['id']}/validate",
        headers=_headers(admin_tokens),
    )
    assert missing.status_code == 422
    assert missing.json()["detail"] == "AGENT_VERSION_REQUIRED"

    first = await client.post(
        f"/admin/api/v1/agents/{agent['id']}/versions",
        json=_agent_version(),
        headers=_headers(admin_tokens),
    )
    assert first.status_code == 201, first.text
    assert len(first.json()["content_sha256"]) == 64
    validated = await client.post(
        f"/admin/api/v1/agents/{agent['id']}/validate",
        headers=_headers(admin_tokens),
    )
    assert validated.status_code == 200, validated.text
    assert validated.json()["status"] == "validated"

    overlap_body = {
        **_agent_version(),
        "min_version": "1.5.0",
        "max_version_exclusive": "3.0.0",
    }
    overlap = await client.post(
        f"/admin/api/v1/agents/{agent['id']}/versions",
        json=overlap_body,
        headers=_headers(admin_tokens),
    )
    assert overlap.status_code == 201
    rejected = await client.post(
        f"/admin/api/v1/agents/{agent['id']}/validate",
        headers=_headers(admin_tokens),
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == "AGENT_VERSION_RANGE_OVERLAP"


@pytest.mark.asyncio
async def test_catalog_requests_reject_unknown_fields_and_invalid_semver(
    client: AsyncClient,
    admin_tokens: dict[str, object],
) -> None:
    bad_agent = await client.post(
        "/admin/api/v1/agents",
        json={**_agent_body("opencode"), "tenant_id": str(uuid.uuid4())},
        headers=_headers(admin_tokens),
    )
    assert bad_agent.status_code == 422
    agent = (
        await client.post(
            "/admin/api/v1/agents",
            json=_agent_body("opencode"),
            headers=_headers(admin_tokens),
        )
    ).json()
    invalid = await client.post(
        f"/admin/api/v1/agents/{agent['id']}/versions",
        json={**_agent_version(), "min_version": "latest"},
        headers=_headers(admin_tokens),
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"] == "CATALOG_SEMVER_INVALID"


@pytest.mark.asyncio
async def test_model_constraints_and_provider_url_policy(
    client: AsyncClient,
    admin_tokens: dict[str, object],
) -> None:
    model = await client.post(
        "/admin/api/v1/models",
        json=_model_body(),
        headers=_headers(admin_tokens),
    )
    assert model.status_code == 201, model.text
    assert model.json()["catalog_revision"] == 1

    invalid_model = await client.post(
        "/admin/api/v1/models",
        json={**_model_body("bad"), "max_output_tokens": 30_000},
        headers=_headers(admin_tokens),
    )
    assert invalid_model.status_code == 422
    assert invalid_model.json()["detail"] == "MODEL_CAPABILITY_INVALID"

    provider = await client.post(
        "/admin/api/v1/providers",
        json=_provider_body(),
        headers=_headers(admin_tokens),
    )
    assert provider.status_code == 201, provider.text
    assert provider.json()["base_url"] == "https://api.openai.com/v1"
    for invalid_url in ("http://api.example.com", "https://127.0.0.1/v1"):
        rejected = await client.post(
            "/admin/api/v1/providers",
            json={**_provider_body(f"p{uuid.uuid4().hex[:8]}"), "base_url": invalid_url},
            headers=_headers(admin_tokens),
        )
        assert rejected.status_code == 422


@pytest.mark.asyncio
async def test_bindings_validate_ranges_and_request_defaults(
    client: AsyncClient,
    admin_tokens: dict[str, object],
) -> None:
    agent = (
        await client.post(
            "/admin/api/v1/agents",
            json=_agent_body("binding_agent"),
            headers=_headers(admin_tokens),
        )
    ).json()
    await client.post(
        f"/admin/api/v1/agents/{agent['id']}/versions",
        json=_agent_version(),
        headers=_headers(admin_tokens),
    )
    model = (
        await client.post(
            "/admin/api/v1/models",
            json=_model_body("binding-model"),
            headers=_headers(admin_tokens),
        )
    ).json()
    binding = await client.post(
        f"/admin/api/v1/agents/{agent['id']}/model-bindings",
        json={
            "model_id": model["id"],
            "min_agent_version": "1.1.0",
            "max_agent_version_exclusive": "1.9.0",
        },
        headers=_headers(admin_tokens),
    )
    assert binding.status_code == 201, binding.text

    provider = (
        await client.post(
            "/admin/api/v1/providers",
            json=_provider_body("binding_provider"),
            headers=_headers(admin_tokens),
        )
    ).json()
    forbidden = await client.post(
        f"/admin/api/v1/providers/{provider['id']}/model-bindings",
        json={
            "model_id": model["id"],
            "provider_model_name": "gpt-5",
            "request_defaults": {"model": "override"},
        },
        headers=_headers(admin_tokens),
    )
    assert forbidden.status_code == 422
    assert forbidden.json()["detail"] == "PROVIDER_REQUEST_DEFAULTS_FORBIDDEN"


@pytest.mark.asyncio
async def test_published_revision_is_immutable_and_clone_keeps_logical_key(
    client: AsyncClient,
    admin_tokens: dict[str, object],
    db_session: AsyncSession,
) -> None:
    created = await client.post(
        "/admin/api/v1/agents",
        json=_agent_body("immutable_agent"),
        headers=_headers(admin_tokens),
    )
    agent_id = uuid.UUID(created.json()["id"])
    resource = await db_session.get(AgentCatalog, agent_id)
    assert resource is not None
    resource.status = "published"
    await db_session.commit()

    immutable = await client.patch(
        f"/admin/api/v1/agents/{agent_id}",
        json={"display_name": "Illegal"},
        headers=_headers(admin_tokens, **{"If-Match": "1"}),
    )
    assert immutable.status_code == 409
    clone = await client.post(
        f"/admin/api/v1/agents/{agent_id}/revisions",
        headers=_headers(admin_tokens),
    )
    assert clone.status_code == 201, clone.text
    assert clone.json()["key"] == "immutable_agent"
    assert clone.json()["catalog_revision"] == 2
    assert clone.json()["status"] == "draft"


@pytest.mark.asyncio
async def test_lists_use_items_cursor_contract(
    client: AsyncClient,
    admin_tokens: dict[str, object],
) -> None:
    await client.post(
        "/admin/api/v1/agents",
        json=_agent_body("list_agent"),
        headers=_headers(admin_tokens),
    )
    response = await client.get(
        "/admin/api/v1/agents",
        headers=_headers(admin_tokens),
    )
    assert response.status_code == 200
    assert response.json()["items"]
    assert response.json()["next_cursor"] is None
