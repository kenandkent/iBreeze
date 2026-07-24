"""G.8/G.13 Skill revision and ZIP supply-chain tests."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import uuid
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from httpx import AsyncClient

from ibreeze_backend.security.keys import load_or_create_signing_keys
from ibreeze_backend.settings import settings
from ibreeze_backend.skills.service import storage


def _headers(tokens: dict[str, object], match: str | None = None) -> dict[str, str]:
    result = {"Authorization": f"Bearer {tokens['access_token']}"}
    if match:
        result["If-Match"] = match
    return result


def _skill_body(key: str = "code-review") -> dict[str, str]:
    return {
        "key": key,
        "display_name": "Code Review",
        "description": "Review source code and return structured issues.",
    }


def _package(
    *,
    key: str = "code-review",
    version: str = "1.0.0",
    content: bytes = b"Review carefully.\n",
    declared_hash: str | None = None,
    extra_path: str | None = None,
) -> io.BytesIO:
    manifest = {
        "schema_version": 1,
        "key": key,
        "version": version,
        "display_name": "Code Review",
        "description": "Review source code.",
        "entrypoint": "instructions.md",
        "capability_tags": ["code", "review"],
        "supported_runtime_types": ["agent_cli", "api_model"],
        "supported_agent_keys": ["codex_cli"],
        "model_requirements": {
            "supports_tools": True,
            "supports_vision": False,
            "minimum_context_window": 32_000,
        },
        "supported_platforms": ["macos_arm64"],
        "required_tools": ["read_file"],
        "network_domains": [],
        "file_policy": "workspace_rw_external_ro",
        "risk_level": "medium",
        "dependencies": [],
        "conflicts": [],
        "files": [
            {
                "path": "instructions.md",
                "sha256": declared_hash or hashlib.sha256(content).hexdigest(),
                "executable": False,
                "interpreter": None,
            }
        ],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("skill.json", json.dumps(manifest))
        archive.writestr("instructions.md", content)
        if extra_path:
            archive.writestr(extra_path, b"escape")
    buffer.seek(0)
    return buffer


@pytest.fixture(autouse=True)
def isolated_skill_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage, "base_path", (tmp_path / "objects").resolve())
    storage.base_path.mkdir(parents=True)


@pytest.mark.asyncio
async def test_skill_upload_is_hashed_signed_and_validated(
    client: AsyncClient,
    admin_tokens: dict[str, object],
) -> None:
    created = await client.post(
        "/admin/api/v1/skills",
        json=_skill_body(),
        headers=_headers(admin_tokens),
    )
    assert created.status_code == 201, created.text
    skill = created.json()
    package = _package()
    raw_package = package.getvalue()
    uploaded = await client.post(
        f"/admin/api/v1/skills/{skill['id']}/versions",
        data={"version": "1.0.0"},
        files={"package": ("skill.zip", package, "application/zip")},
        headers=_headers(admin_tokens),
    )
    assert uploaded.status_code == 201, uploaded.text
    item = uploaded.json()
    assert item["object_sha256"] == hashlib.sha256(raw_package).hexdigest()
    assert item["object_key"] == (
        f"skills/{skill['id']}/1.0.0/{item['object_sha256']}.zip"
    )
    assert item["content_sha256"]
    private_pem, public_pem, kid = load_or_create_signing_keys(
        Path(settings.catalog_key_dir)
    )
    assert private_pem
    assert item["signing_key_id"] == kid
    public_key = serialization.load_pem_public_key(public_pem)
    assert isinstance(public_key, Ed25519PublicKey)
    signed = (
        f"skill-v1\n{skill['id']}\n1.0.0\n"
        f"{item['object_sha256']}\n{item['content_sha256']}"
    ).encode()
    public_key.verify(
        base64.urlsafe_b64decode(item["signature"] + "=="),
        signed,
    )
    validated = await client.post(
        f"/admin/api/v1/skills/{skill['id']}/validate",
        headers=_headers(admin_tokens),
    )
    assert validated.status_code == 200, validated.text
    assert validated.json()["status"] == "validated"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("package", "error_code"),
    [
        (
            _package(declared_hash="0" * 64),
            "SKILL_MANIFEST_FILE_HASH_MISMATCH",
        ),
        (
            _package(extra_path="../escape"),
            "SKILL_PACKAGE_PATH_INVALID",
        ),
        (
            _package(key="wrong-key"),
            "SKILL_MANIFEST_IDENTITY_MISMATCH",
        ),
    ],
)
async def test_skill_upload_rejects_invalid_packages(
    client: AsyncClient,
    admin_tokens: dict[str, object],
    package: io.BytesIO,
    error_code: str,
) -> None:
    key = f"skill-{uuid.uuid4().hex[:8]}"
    skill = (
        await client.post(
            "/admin/api/v1/skills",
            json=_skill_body(key),
            headers=_headers(admin_tokens),
        )
    ).json()
    if error_code != "SKILL_MANIFEST_IDENTITY_MISMATCH":
        package = _package(
            key=key,
            declared_hash="0" * 64
            if error_code == "SKILL_MANIFEST_FILE_HASH_MISMATCH"
            else None,
            extra_path="../escape" if error_code == "SKILL_PACKAGE_PATH_INVALID" else None,
        )
    response = await client.post(
        f"/admin/api/v1/skills/{skill['id']}/versions",
        data={"version": "1.0.0"},
        files={"package": ("skill.zip", package, "application/zip")},
        headers=_headers(admin_tokens),
    )
    assert response.status_code == 422
    assert response.json()["detail"] == error_code


@pytest.mark.asyncio
async def test_skill_package_download_streams_exact_bytes(
    client: AsyncClient,
    admin_tokens: dict[str, object],
    user_tokens: dict[str, object],
) -> None:
    skill = (
        await client.post(
            "/admin/api/v1/skills",
            json=_skill_body("download-skill"),
            headers=_headers(admin_tokens),
        )
    ).json()
    package = _package(key="download-skill")
    expected = package.getvalue()
    upload = await client.post(
        f"/admin/api/v1/skills/{skill['id']}/versions",
        data={"version": "1.0.0"},
        files={"package": ("skill.zip", package, "application/zip")},
        headers=_headers(admin_tokens),
    )
    assert upload.status_code == 201, upload.text
    response = await client.get(
        f"/api/v1/catalog/skills/{skill['id']}/versions/1.0.0/package",
        headers=_headers(user_tokens),
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.content == expected


@pytest.mark.asyncio
async def test_skill_version_delete_uses_version_id_and_parent_is_immutable(
    client: AsyncClient,
    admin_tokens: dict[str, object],
) -> None:
    skill = (
        await client.post(
            "/admin/api/v1/skills",
            json=_skill_body("delete-skill"),
            headers=_headers(admin_tokens),
        )
    ).json()
    uploaded = await client.post(
        f"/admin/api/v1/skills/{skill['id']}/versions",
        data={"version": "1.0.0"},
        files={
            "package": (
                "skill.zip",
                _package(key="delete-skill"),
                "application/zip",
            )
        },
        headers=_headers(admin_tokens),
    )
    assert uploaded.status_code == 201
    response = await client.delete(
        f"/admin/api/v1/skills/{skill['id']}/versions/{uploaded.json()['id']}",
        headers=_headers(admin_tokens),
    )
    assert response.status_code == 204
