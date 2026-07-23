"""Catalog management tests."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_agent(client: AsyncClient, admin_tokens):
    response = await client.post(
        "/admin/api/v1/catalog/agents",
        json={"key": "test_agent", "display_name": "Test Agent", "description": "A test agent"},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["key"] == "test_agent"
    assert data["status"] == "draft"


@pytest.mark.asyncio
async def test_create_model(client: AsyncClient, admin_tokens):
    response = await client.post(
        "/admin/api/v1/catalog/models",
        json={"provider_key": "openai", "model_key": "gpt-4", "display_name": "GPT-4",
              "context_window": 8192, "supports_tools": True, "supports_streaming": True, "supports_vision": False},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["model_key"] == "gpt-4"
    assert data["status"] == "draft"


@pytest.mark.asyncio
async def test_create_provider(client: AsyncClient, admin_tokens):
    response = await client.post(
        "/admin/api/v1/catalog/providers",
        json={"display_name": "OpenAI", "base_url": "https://api.openai.com/v1", "api_protocol": "openai"},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["display_name"] == "OpenAI"
    assert data["status"] == "draft"


@pytest.mark.asyncio
async def test_status_transition(client: AsyncClient, admin_tokens):
    create = await client.post(
        "/admin/api/v1/catalog/agents",
        json={"key": "test_agent_2", "display_name": "Test Agent 2", "description": "A test agent"},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    agent_id = create.json()["id"]

    r = await client.patch(
        f"/admin/api/v1/catalog/agents/{agent_id}/status",
        json={"status": "validated"},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "validated"

    r = await client.patch(
        f"/admin/api/v1/catalog/agents/{agent_id}/status",
        json={"status": "published"},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "published"


@pytest.mark.asyncio
async def test_invalid_status_transition(client: AsyncClient, admin_tokens):
    create = await client.post(
        "/admin/api/v1/catalog/agents",
        json={"key": "test_agent_3", "display_name": "Test Agent 3", "description": "A test agent"},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    agent_id = create.json()["id"]

    r = await client.patch(
        f"/admin/api/v1/catalog/agents/{agent_id}/status",
        json={"status": "published"},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_published_resource_immutable(client: AsyncClient, admin_tokens):
    create = await client.post(
        "/admin/api/v1/catalog/agents",
        json={"key": "test_agent_4", "display_name": "Test Agent 4", "description": "A test agent"},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    agent_id = create.json()["id"]

    await client.patch(
        f"/admin/api/v1/catalog/agents/{agent_id}/status",
        json={"status": "validated"},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    await client.patch(
        f"/admin/api/v1/catalog/agents/{agent_id}/status",
        json={"status": "published"},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )

    r = await client.patch(
        f"/admin/api/v1/catalog/agents/{agent_id}",
        json={"display_name": "Modified Name"},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_create_compatibility_rule(client: AsyncClient, admin_tokens):
    response = await client.post(
        "/admin/api/v1/compatibility/rules",
        json={"subject_type": "agent", "subject_version_range": {"min": "0.1.0", "max": "1.0.0"},
              "dependency_type": "model", "dependency_version_range": {"min": "1.0.0", "max": "2.0.0"},
              "result": "allow", "reason_code": "tested", "priority": 100},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 201
    assert response.json()["result"] == "allow"


@pytest.mark.asyncio
async def test_list_agents(client: AsyncClient, admin_tokens):
    response = await client.get(
        "/admin/api/v1/catalog/agents",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data


@pytest.mark.asyncio
async def test_list_models(client: AsyncClient, admin_tokens):
    response = await client.get(
        "/admin/api/v1/catalog/models",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "models" in data


@pytest.mark.asyncio
async def test_list_providers(client: AsyncClient, admin_tokens):
    response = await client.get(
        "/admin/api/v1/catalog/providers",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
