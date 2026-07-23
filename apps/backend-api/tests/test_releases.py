"""Release management tests."""
import io
import uuid
import zipfile
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.models.catalog_release import CatalogRelease
from ibreeze_backend.models.emergency_disable import EmergencyDisableRelease as EmergencyDisable
from ibreeze_backend.models.skill import Skill
from ibreeze_backend.skills.service import install_skill


def _make_valid_zip() -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("manifest.json", '{"name": "test_skill"}')
        zf.writestr("main.py", "print('hello')")
    buffer.seek(0)
    return buffer


@pytest.mark.asyncio
async def test_create_release(client: AsyncClient, admin_tokens: dict):
    """Test creating a new release."""
    response = await client.post(
        "/admin/api/v1/catalog/releases",
        json={"version": "2024.01.15", "notes": "Test release"},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["version"] == "2024.01.15"
    assert data["status"] == "draft"
    assert "id" in data
    assert data["release_sequence"] == 1
    assert "signing_key_id" in data


@pytest.mark.asyncio
async def test_publish_release(client: AsyncClient, admin_tokens: dict):
    """Test publishing a release."""
    create_resp = await client.post(
        "/admin/api/v1/catalog/releases",
        json={"version": "2024.02.01"},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert create_resp.status_code == 201
    release_id = create_resp.json()["id"]

    response = await client.post(
        f"/admin/api/v1/catalog/releases/{release_id}/publish",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "published"
    assert data["version"] == "2024.02.01"
    assert "published_at" in data


@pytest.mark.asyncio
async def test_publish_nonexistent_release(client: AsyncClient, admin_tokens: dict):
    """Test publishing a release that does not exist returns 404."""
    fake_id = uuid.uuid4()
    response = await client.post(
        f"/admin/api/v1/catalog/releases/{fake_id}/publish",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Release not found"


@pytest.mark.asyncio
async def test_publish_already_published(client: AsyncClient, admin_tokens: dict):
    """Test publishing an already-published release returns 400."""
    create_resp = await client.post(
        "/admin/api/v1/catalog/releases",
        json={"version": "2024.03.01"},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    release_id = create_resp.json()["id"]

    await client.post(
        f"/admin/api/v1/catalog/releases/{release_id}/publish",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )

    response = await client.post(
        f"/admin/api/v1/catalog/releases/{release_id}/publish",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Release already published"


@pytest.mark.asyncio
async def test_get_latest_manifest(
    client: AsyncClient, admin_tokens: dict, db_session: AsyncSession, tmp_path: Path
):
    """Test getting the latest published manifest."""
    skill_id = str(uuid.uuid4())
    zip_path = tmp_path / "manifest_skill.zip"
    zip_path.write_bytes(_make_valid_zip().read())
    await install_skill(db_session, skill_id, "1.0.0", zip_path)
    await db_session.commit()

    create_resp = await client.post(
        "/admin/api/v1/catalog/releases",
        json={"version": "2024.04.01"},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    release_id = create_resp.json()["id"]

    await client.post(
        f"/admin/api/v1/catalog/releases/{release_id}/publish",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )

    response = await client.get("/api/v1/catalog/manifest")
    assert response.status_code == 200
    manifest = response.json()
    assert manifest["release_sequence"] == 1
    assert len(manifest["resources"]) >= 1


@pytest.mark.asyncio
async def test_create_emergency_disable(
    client: AsyncClient, admin_tokens: dict, db_session: AsyncSession, tmp_path: Path
):
    """Test creating an emergency disable record."""
    skill_id = str(uuid.uuid4())
    zip_path = tmp_path / "emergency_skill.zip"
    zip_path.write_bytes(_make_valid_zip().read())
    await install_skill(db_session, skill_id, "1.0.0", zip_path)
    await db_session.commit()

    response = await client.post(
        "/admin/api/v1/emergency-disables",
        json={"skill_ids": [skill_id]},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sequence"] == 1
    assert skill_id in data["disabled_skill_ids"]
    assert "created_at" in data

    result = await db_session.execute(
        select(Skill).where(Skill.id == uuid.UUID(skill_id))
    )
    skill = result.scalar_one_or_none()
    assert skill is not None
    assert skill.is_active is False


@pytest.mark.asyncio
async def test_get_latest_emergency_disable(
    client: AsyncClient, admin_tokens: dict
):
    """Test getting the latest emergency disable record."""
    await client.post(
        "/admin/api/v1/emergency-disables",
        json={"skill_ids": [str(uuid.uuid4())]},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    await client.post(
        "/admin/api/v1/emergency-disables",
        json={"skill_ids": [str(uuid.uuid4())]},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )

    response = await client.get(
        "/admin/api/v1/emergency-disables/latest",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sequence"] == 2


@pytest.mark.asyncio
async def test_get_release_by_id(
    client: AsyncClient, admin_tokens: dict
):
    """Test getting a release by its ID."""
    create_resp = await client.post(
        "/admin/api/v1/catalog/releases",
        json={"version": "2024.05.01", "notes": "Test notes"},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    release_id = create_resp.json()["id"]

    response = await client.get(f"/api/v1/catalog/releases/{release_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == release_id
    assert data["version"] == "2024.05.01"
    assert data["notes"] == "Test notes"
    assert data["status"] == "draft"
    assert "manifest" in data
    assert data["release_sequence"] == 1
