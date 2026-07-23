"""Skill management tests."""
import io
import uuid
import zipfile
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.models.skill import Skill
from ibreeze_backend.skills.service import (
    emergency_disable_skill,
    install_skill,
    remove_skill,
)


def _make_zip_buffer(files: dict[str, str]) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    buffer.seek(0)
    return buffer


def _make_valid_zip() -> io.BytesIO:
    return _make_zip_buffer({
        "manifest.json": '{"name": "test_skill"}',
        "main.py": "print('hello')",
    })


@pytest.mark.asyncio
async def test_install_skill_invalid_zip(db_session: AsyncSession, tmp_path: Path):
    """Test that installing a ZIP without manifest.json raises ValueError."""
    skill_id = str(uuid.uuid4())
    buffer = _make_zip_buffer({"main.py": "print('hello')"})
    zip_path = tmp_path / "no_manifest.zip"
    zip_path.write_bytes(buffer.read())

    with pytest.raises(ValueError, match="Missing manifest.json"):
        await install_skill(db_session, skill_id, "1.0.0", zip_path)


@pytest.mark.asyncio
async def test_install_skill_valid(db_session: AsyncSession, tmp_path: Path):
    """Test successfully installing a valid skill via service."""
    skill_id = str(uuid.uuid4())
    zip_path = tmp_path / "valid.zip"
    zip_path.write_bytes(_make_valid_zip().read())

    skill = await install_skill(db_session, skill_id, "1.0.0", zip_path)

    assert str(skill.id) == skill_id
    assert skill.version == "1.0.0"
    assert skill.is_active is True
    assert skill.checksum is not None

    result = await db_session.execute(
        select(Skill).where(Skill.id == uuid.UUID(skill_id))
    )
    saved = result.scalar_one_or_none()
    assert saved is not None


@pytest.mark.asyncio
async def test_remove_skill(db_session: AsyncSession, tmp_path: Path):
    """Test removing an inactive skill."""
    skill_id = str(uuid.uuid4())
    zip_path = tmp_path / "remove.zip"
    zip_path.write_bytes(_make_valid_zip().read())
    await install_skill(db_session, skill_id, "1.0.0", zip_path)

    await emergency_disable_skill(db_session, skill_id)

    removed = await remove_skill(db_session, skill_id, "1.0.0")
    assert removed is True

    result = await db_session.execute(
        select(Skill).where(Skill.id == uuid.UUID(skill_id))
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_remove_skill_nonexistent(db_session: AsyncSession):
    """Test removing a nonexistent skill returns False."""
    removed = await remove_skill(db_session, str(uuid.uuid4()), "1.0.0")
    assert removed is False


@pytest.mark.asyncio
async def test_emergency_disable_skill(db_session: AsyncSession, tmp_path: Path):
    """Test emergency disabling a skill sets is_active to False."""
    skill_id = str(uuid.uuid4())
    zip_path = tmp_path / "disable.zip"
    zip_path.write_bytes(_make_valid_zip().read())
    await install_skill(db_session, skill_id, "1.0.0", zip_path)

    result = await emergency_disable_skill(db_session, skill_id)
    assert result is True

    result = await db_session.execute(
        select(Skill).where(Skill.id == uuid.UUID(skill_id))
    )
    skill = result.scalar_one_or_none()
    assert skill is not None
    assert skill.is_active is False


@pytest.mark.asyncio
async def test_upload_skill_version_endpoint(
    client: AsyncClient, admin_tokens: dict
):
    """Test uploading a skill version via the HTTP endpoint."""
    skill_id = str(uuid.uuid4())
    buffer = _make_valid_zip()

    response = await client.post(
        f"/admin/api/v1/skills/{skill_id}/versions",
        params={"version": "1.0.0"},
        files={"file": ("skill.zip", buffer, "application/zip")},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == skill_id
    assert data["version"] == "1.0.0"
    assert data["is_active"] is True
    assert "checksum" in data


@pytest.mark.asyncio
async def test_download_skill_package(
    client: AsyncClient, admin_tokens: dict
):
    """Test downloading a skill package that exists returns a URL."""
    skill_id = str(uuid.uuid4())
    buffer = _make_valid_zip()

    upload_resp = await client.post(
        f"/admin/api/v1/skills/{skill_id}/versions",
        params={"version": "1.0.0"},
        files={"file": ("skill.zip", buffer, "application/zip")},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert upload_resp.status_code == 201

    response = await client.get(
        f"/api/v1/catalog/skills/{skill_id}/versions/1.0.0/package",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "download_url" in data
    assert data["skill_id"] == skill_id
    assert data["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_remove_skill_version(
    client: AsyncClient, admin_tokens: dict, db_session: AsyncSession, tmp_path: Path
):
    """Test removing a skill version via HTTP."""
    skill_id = str(uuid.uuid4())
    zip_path = tmp_path / "remove_ver.zip"
    zip_path.write_bytes(_make_valid_zip().read())
    await install_skill(db_session, skill_id, "1.0.0", zip_path)
    await db_session.commit()

    response = await client.delete(
        f"/admin/api/v1/skills/{skill_id}/versions/1.0.0",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 400

    await emergency_disable_skill(db_session, skill_id)
    await db_session.commit()

    response = await client.delete(
        f"/admin/api/v1/skills/{skill_id}/versions/1.0.0",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 204
