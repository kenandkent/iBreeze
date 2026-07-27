"""ZIP validation service tests."""

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from ibreeze_backend.services.zip_service import validate_skill_zip


def _make_manifest(
    key: str = "test-skill",
    version: str = "1.0.0",
    files: list[dict] | None = None,
    **overrides,
) -> dict:
    """Build a valid SkillManifest dict."""
    manifest = {
        "schema_version": 1,
        "key": key,
        "version": version,
        "display_name": "Test Skill",
        "description": "A test skill",
        "entrypoint": "main.py",
        "capability_tags": ["test"],
        "supported_runtime_types": ["agent_cli"],
        "supported_agent_keys": ["test-agent"],
        "model_requirements": {
            "supports_tools": True,
            "supports_vision": False,
            "minimum_context_window": 8192,
        },
        "supported_platforms": ["linux"],
        "required_tools": [],
        "network_domains": [],
        "file_policy": "workspace_rw_external_ro",
        "risk_level": "low",
        "dependencies": [],
        "conflicts": [],
        "files": files or [
            {"path": "main.py", "sha256": "", "executable": False, "interpreter": None},
            {"path": "instructions.md", "sha256": "", "executable": False, "interpreter": None},
        ],
    }
    manifest.update(overrides)
    return manifest


def _make_zip_with_manifest(
    manifest: dict,
    extra_files: dict[str, str] | None = None,
) -> bytes:
    """Create a ZIP with skill.json and extra files, computing correct SHA256."""
    files_content = {}
    if extra_files:
        files_content.update(extra_files)

    for f in manifest.get("files", []):
        path = f["path"]
        if path not in files_content:
            files_content[path] = f"content of {path}"

    for f in manifest["files"]:
        path = f["path"]
        content = files_content[path]
        f["sha256"] = hashlib.sha256(content.encode()).hexdigest()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("skill.json", json.dumps(manifest, separators=(",", ":")))
        for path, content in files_content.items():
            zf.writestr(path, content)
    return buf.getvalue()


def _write_zip(tmp_path: Path, name: str, data: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(data)
    return p


# ---------------------------------------------------------------------------
# validate_skill_zip - success cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_skill_zip(tmp_path: Path):
    manifest = _make_manifest()
    data = _make_zip_with_manifest(manifest, {"instructions.md": "# Instructions"})
    path = _write_zip(tmp_path, "valid.zip", data)
    result_manifest, object_sha256, content_sha256 = validate_skill_zip(
        path, expected_key="test-skill", expected_version="1.0.0"
    )
    assert result_manifest.key == "test-skill"
    assert result_manifest.version == "1.0.0"
    assert len(object_sha256) == 64
    assert len(content_sha256) == 64


# ---------------------------------------------------------------------------
# Size validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_zip_rejected(tmp_path: Path):
    path = _write_zip(tmp_path, "empty.zip", b"")
    with pytest.raises(ValueError, match="SKILL_PACKAGE_SIZE_INVALID"):
        validate_skill_zip(path, expected_key="k", expected_version="1")


@pytest.mark.asyncio
async def test_oversized_zip_rejected(tmp_path: Path):
    size = 51 * 1024 * 1024
    path = _write_zip(tmp_path, "huge.zip", b"x" * size)
    with pytest.raises(ValueError, match="SKILL_PACKAGE_SIZE_INVALID"):
        validate_skill_zip(path, expected_key="k", expected_version="1")


# ---------------------------------------------------------------------------
# ZIP structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bad_zip_format_rejected(tmp_path: Path):
    path = _write_zip(tmp_path, "bad.zip", b"not a zip file")
    with pytest.raises(ValueError, match="SKILL_PACKAGE_INVALID_ZIP"):
        validate_skill_zip(path, expected_key="k", expected_version="1")


@pytest.mark.asyncio
async def test_too_many_entries_rejected(tmp_path: Path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("skill.json", json.dumps(_make_manifest(), separators=(",", ":")))
        for i in range(1001):
            zf.writestr(f"file_{i}.txt", "x")
    path = _write_zip(tmp_path, "many.zip", buf.getvalue())
    with pytest.raises(ValueError, match="SKILL_PACKAGE_ENTRY_LIMIT"):
        validate_skill_zip(path, expected_key="test-skill", expected_version="1.0.0")


@pytest.mark.asyncio
async def test_path_traversal_rejected(tmp_path: Path):
    manifest = _make_manifest()
    # We need to add a traversal entry manually, recreate with malicious path
    buf2 = io.BytesIO()
    with zipfile.ZipFile(buf2, "w") as zf:
        zf.writestr("skill.json", json.dumps(manifest, separators=(",", ":")))
        zf.writestr("main.py", "x")
        zf.writestr("instructions.md", "x")
        zf.writestr("../evil.py", "evil")
    path = _write_zip(tmp_path, "traversal.zip", buf2.getvalue())
    with pytest.raises(ValueError, match="SKILL_PACKAGE_PATH_INVALID"):
        validate_skill_zip(path, expected_key="test-skill", expected_version="1.0.0")


@pytest.mark.asyncio
async def test_duplicate_path_rejected(tmp_path: Path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("skill.json", json.dumps(_make_manifest(), separators=(",", ":")))
        zf.writestr("main.py", "x")
        zf.writestr("main.py", "y")  # duplicate
        zf.writestr("instructions.md", "z")
    path = _write_zip(tmp_path, "dup.zip", buf.getvalue())
    with pytest.raises(ValueError, match="SKILL_PACKAGE_DUPLICATE_PATH"):
        validate_skill_zip(path, expected_key="test-skill", expected_version="1.0.0")


# ---------------------------------------------------------------------------
# Manifest file validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_skill_json_rejected(tmp_path: Path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("main.py", "x")
    path = _write_zip(tmp_path, "no_manifest.zip", buf.getvalue())
    with pytest.raises(ValueError, match="SKILL_MANIFEST_MISSING"):
        validate_skill_zip(path, expected_key="k", expected_version="1")


@pytest.mark.asyncio
async def test_missing_instructions_md_rejected(tmp_path: Path):
    manifest = _make_manifest()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("skill.json", json.dumps(manifest, separators=(",", ":")))
        zf.writestr("main.py", "x")
    path = _write_zip(tmp_path, "no_instr.zip", buf.getvalue())
    with pytest.raises(ValueError, match="SKILL_INSTRUCTIONS_MISSING"):
        validate_skill_zip(path, expected_key="test-skill", expected_version="1.0.0")


@pytest.mark.asyncio
async def test_invalid_manifest_json_rejected(tmp_path: Path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("skill.json", b"not json")
        zf.writestr("instructions.md", "x")
    path = _write_zip(tmp_path, "bad_json.zip", buf.getvalue())
    with pytest.raises(ValueError, match="SKILL_MANIFEST_INVALID"):
        validate_skill_zip(path, expected_key="k", expected_version="1")


@pytest.mark.asyncio
async def test_manifest_identity_mismatch_rejected(tmp_path: Path):
    manifest = _make_manifest(key="wrong-key")
    data = _make_zip_with_manifest(manifest, {"instructions.md": "# Instructions"})
    path = _write_zip(tmp_path, "bad_id.zip", data)
    with pytest.raises(ValueError, match="SKILL_MANIFEST_IDENTITY_MISMATCH"):
        validate_skill_zip(path, expected_key="expected-key", expected_version="1.0.0")


# ---------------------------------------------------------------------------
# File hash validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_hash_mismatch_rejected(tmp_path: Path):
    main_content = "content of main.py"
    instr_content = "# Instructions"
    real_instr_hash = hashlib.sha256(instr_content.encode()).hexdigest()
    manifest = _make_manifest()
    manifest["files"][0]["sha256"] = "a" * 64  # wrong hash for main.py
    manifest["files"][1]["sha256"] = real_instr_hash  # correct for instructions.md
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("skill.json", json.dumps(manifest, separators=(",", ":")))
        zf.writestr("main.py", main_content)
        zf.writestr("instructions.md", instr_content)
    path = _write_zip(tmp_path, "bad_hash.zip", buf.getvalue())
    with pytest.raises(ValueError, match="SKILL_MANIFEST_FILE_HASH_MISMATCH"):
        validate_skill_zip(path, expected_key="test-skill", expected_version="1.0.0")


@pytest.mark.asyncio
async def test_missing_declared_file_rejected(tmp_path: Path):
    manifest = _make_manifest(files=[
        {"path": "missing.py", "sha256": "a" * 64, "executable": False, "interpreter": None},
        {"path": "instructions.md", "sha256": "", "executable": False, "interpreter": None},
    ])
    data = _make_zip_with_manifest(manifest, {"instructions.md": "# Instructions"})
    path = _write_zip(tmp_path, "missing_file.zip", data)
    with pytest.raises(ValueError, match="SKILL_MANIFEST_FILE_SET_INVALID"):
        validate_skill_zip(path, expected_key="test-skill", expected_version="1.0.0")


# ---------------------------------------------------------------------------
# Entrypoint validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_entrypoint_not_in_declared_files_rejected(tmp_path: Path):
    manifest = _make_manifest(entrypoint="nonexistent.py")
    data = _make_zip_with_manifest(manifest, {"instructions.md": "# Instructions"})
    path = _write_zip(tmp_path, "bad_entry.zip", data)
    with pytest.raises(ValueError, match="SKILL_MANIFEST_FILE_SET_INVALID"):
        validate_skill_zip(path, expected_key="test-skill", expected_version="1.0.0")


# ---------------------------------------------------------------------------
# Network domains validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_network_domain_rejected(tmp_path: Path):
    manifest = _make_manifest(network_domains=["http://evil.com"])
    data = _make_zip_with_manifest(manifest, {"instructions.md": "# Instructions"})
    path = _write_zip(tmp_path, "bad_domain.zip", data)
    with pytest.raises(ValueError, match="SKILL_NETWORK_DOMAIN_INVALID"):
        validate_skill_zip(path, expected_key="test-skill", expected_version="1.0.0")
