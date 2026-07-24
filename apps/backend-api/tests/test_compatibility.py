"""Compatibility-rule contract tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.compatibility.models import CompatibilityRule


def _body() -> dict[str, object]:
    return {
        "subject_type": "agent",
        "subject_id": str(uuid.uuid4()),
        "subject_version_range": ">=1.0.0 <2.0.0",
        "dependency_type": "model",
        "dependency_key": "openai/gpt-5",
        "dependency_version_range": "^1.0.0",
        "decision": "allow",
        "reason_code": "contract_tested",
        "priority": 100,
    }


def _headers(tokens: dict[str, object], match: str | None = None) -> dict[str, str]:
    result = {"Authorization": f"Bearer {tokens['access_token']}"}
    if match is not None:
        result["If-Match"] = match
    return result


@pytest.mark.asyncio
async def test_rule_crud_validate_and_locking(
    client: AsyncClient,
    admin_tokens: dict[str, object],
) -> None:
    created = await client.post(
        "/admin/api/v1/compatibility-rules",
        json=_body(),
        headers=_headers(admin_tokens),
    )
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["status"] == "draft"
    assert item["version"] == 1

    missing_match = await client.patch(
        f"/admin/api/v1/compatibility-rules/{item['id']}",
        json={"decision": "deny"},
        headers=_headers(admin_tokens),
    )
    assert missing_match.status_code == 428
    updated = await client.patch(
        f"/admin/api/v1/compatibility-rules/{item['id']}",
        json={"decision": "deny"},
        headers=_headers(admin_tokens, "1"),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["decision"] == "deny"
    assert updated.json()["version"] == 2

    validated = await client.post(
        f"/admin/api/v1/compatibility-rules/{item['id']}/validate",
        headers=_headers(admin_tokens),
    )
    assert validated.status_code == 200, validated.text
    assert validated.json()["status"] == "validated"


@pytest.mark.asyncio
async def test_rule_validation_rejects_ambiguous_version_range(
    client: AsyncClient,
    admin_tokens: dict[str, object],
) -> None:
    created = await client.post(
        "/admin/api/v1/compatibility-rules",
        json={**_body(), "subject_version_range": "latest"},
        headers=_headers(admin_tokens),
    )
    assert created.status_code == 201
    response = await client.post(
        f"/admin/api/v1/compatibility-rules/{created.json()['id']}/validate",
        headers=_headers(admin_tokens),
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "COMPATIBILITY_VERSION_RANGE_INVALID"


@pytest.mark.asyncio
async def test_published_rule_is_immutable(
    client: AsyncClient,
    admin_tokens: dict[str, object],
    db_session: AsyncSession,
) -> None:
    created = await client.post(
        "/admin/api/v1/compatibility-rules",
        json=_body(),
        headers=_headers(admin_tokens),
    )
    rule = await db_session.get(CompatibilityRule, uuid.UUID(created.json()["id"]))
    assert rule is not None
    rule.status = "published"
    await db_session.commit()
    response = await client.delete(
        f"/admin/api/v1/compatibility-rules/{rule.id}",
        headers=_headers(admin_tokens, "1"),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "CATALOG_REVISION_IMMUTABLE"


@pytest.mark.asyncio
async def test_rule_list_uses_cursor_shape(
    client: AsyncClient,
    admin_tokens: dict[str, object],
) -> None:
    await client.post(
        "/admin/api/v1/compatibility-rules",
        json=_body(),
        headers=_headers(admin_tokens),
    )
    response = await client.get(
        "/admin/api/v1/compatibility-rules",
        headers=_headers(admin_tokens),
    )
    assert response.status_code == 200
    assert response.json()["items"]
    assert response.json()["next_cursor"] is None
