"""Compatibility rule tests."""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.compatibility.service import (
    create_rule,
    delete_rule,
    evaluate,
    get_rule,
    list_rules,
    update_rule,
)

_RULE_ARGS = {
    "subject_type": "agent",
    "subject_version_range": {"min": "0.1.0", "max": "1.0.0"},
    "dependency_type": "model",
    "dependency_version_range": {"min": "1.0.0", "max": "2.0.0"},
    "result": "deny",
    "reason_code": "tested",
    "priority": 100,
}


# ---------------------------------------------------------------------------
# Service-level CRUD tests (avoid response_model serialisation issues)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_rule(db_session: AsyncSession):
    """Test creating a compatibility rule via service."""
    rule = await create_rule(db_session, **_RULE_ARGS)
    assert rule.subject_type == "agent"
    assert rule.dependency_type == "model"
    assert rule.result == "deny"
    assert rule.reason_code == "tested"
    assert rule.priority == 100
    assert rule.id is not None


@pytest.mark.asyncio
async def test_create_rule_allow(db_session: AsyncSession):
    """Test creating a rule with allow result."""
    rule = await create_rule(db_session, **{**_RULE_ARGS, "result": "allow"})
    assert rule.result == "allow"


@pytest.mark.asyncio
async def test_create_rule_deny(db_session: AsyncSession):
    """Test creating a rule with deny result."""
    rule = await create_rule(db_session, **_RULE_ARGS)
    assert rule.result == "deny"


@pytest.mark.asyncio
async def test_list_rules(db_session: AsyncSession):
    """Test listing compatibility rules."""
    await create_rule(db_session, **_RULE_ARGS)
    await create_rule(db_session, **{
        **_RULE_ARGS,
        "subject_type": "skill",
        "dependency_type": "agent",
    })

    rules, total = await list_rules(db_session, skip=0, limit=20)
    assert total >= 2
    assert len(rules) >= 2


@pytest.mark.asyncio
async def test_get_rule(db_session: AsyncSession):
    """Test getting a specific rule by id."""
    rule = await create_rule(db_session, **_RULE_ARGS)

    fetched = await get_rule(db_session, rule.id)
    assert fetched is not None
    assert fetched.id == rule.id
    assert fetched.result == "deny"


@pytest.mark.asyncio
async def test_get_rule_not_found(db_session: AsyncSession):
    """Test getting a nonexistent rule returns None."""
    fake_id = uuid.uuid4()
    result = await get_rule(db_session, fake_id)
    assert result is None


@pytest.mark.asyncio
async def test_update_rule(db_session: AsyncSession):
    """Test updating a compatibility rule."""
    rule = await create_rule(db_session, **_RULE_ARGS)

    updated = await update_rule(
        db_session, rule.id,
        result="allow",
        reason_code="updated_reason",
        priority=None,
        subject_type=None,
        subject_version_range=None,
        dependency_type=None,
        dependency_version_range=None,
    )
    assert updated.result == "allow"
    assert updated.reason_code == "updated_reason"
    assert updated.priority == _RULE_ARGS["priority"]


@pytest.mark.asyncio
async def test_delete_rule(db_session: AsyncSession):
    """Test deleting a compatibility rule."""
    rule = await create_rule(db_session, **_RULE_ARGS)

    await delete_rule(db_session, rule.id)

    fetched = await get_rule(db_session, rule.id)
    assert fetched is None


# ---------------------------------------------------------------------------
# HTTP-based evaluate tests (returns plain dict, no response_model)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evaluate_allow(db_session: AsyncSession, client: AsyncClient, admin_tokens: dict):
    """Test evaluation returns allow when no deny rule matches."""
    await create_rule(db_session, **{**_RULE_ARGS, "result": "allow", "priority": 50})
    await db_session.commit()

    response = await client.post(
        "/admin/api/v1/compatibility/evaluate",
        json={
            "subject_type": "agent",
            "subject_version": "0.5.0",
            "dependency_type": "model",
            "dependency_version": "1.5.0",
        },
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["result"] == "allow"


@pytest.mark.asyncio
async def test_evaluate_deny_wins(db_session: AsyncSession, client: AsyncClient, admin_tokens: dict):
    """Test that deny overrides allow at the same priority."""
    for result in ("allow", "deny"):
        await create_rule(db_session, **{
            **_RULE_ARGS,
            "result": result,
            "reason_code": f"rule_{result}",
            "priority": 100,
        })
    await db_session.commit()

    response = await client.post(
        "/admin/api/v1/compatibility/evaluate",
        json={
            "subject_type": "agent",
            "subject_version": "0.5.0",
            "dependency_type": "model",
            "dependency_version": "1.5.0",
        },
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["result"] == "deny"
    assert data["reason_code"] == "rule_deny"


@pytest.mark.asyncio
async def test_evaluate_no_match(client: AsyncClient, admin_tokens: dict):
    """Test evaluation returns allow when no rule matches."""
    response = await client.post(
        "/admin/api/v1/compatibility/evaluate",
        json={
            "subject_type": "unknown_type",
            "subject_version": "0.5.0",
            "dependency_type": "unknown_dep",
            "dependency_version": "1.5.0",
        },
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["result"] == "allow"
    assert data["reason_code"] is None
    assert data["matched_rule_id"] is None
