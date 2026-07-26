"""Security tests for backup archive (R09).

- SEC-BACK-001: Archive path traversal prevention
- SEC-BACK-002: Archive member validation (only regular files)
- SEC-BACK-003: Sensitive file exclusion
"""

from __future__ import annotations

import io
import json
import os
import tarfile
import tempfile
from pathlib import Path

import pytest
import zstandard as zstd

from ibreeze.backup.packager import verify_backup_package


def _create_tar_zst(archive_path: str, members: list[dict]) -> str:
    """Helper to create a tar.zst archive with given members."""
    with open(archive_path, "wb") as f:
        cctx = zstd.ZstdCompressor()
        with cctx.stream_writer(f) as writer:
            with tarfile.open(fileobj=writer, mode="w") as tar:
                for member in members:
                    if member.get("type") == "symlink":
                        tinfo = tarfile.TarInfo(name=member["name"])
                        tinfo.type = tarfile.SYMTYPE
                        tinfo.linkname = member.get("link", "")
                        tar.addfile(tinfo)
                    elif member.get("type") == "dir":
                        tinfo = tarfile.TarInfo(name=member["name"])
                        tinfo.type = tarfile.DIRTYPE
                        tar.addfile(tinfo)
                    else:
                        data = member.get("data", b"")
                        tinfo = tarfile.TarInfo(name=member["name"])
                        tinfo.size = len(data)
                        tar.addfile(tinfo, io.BytesIO(data))
    return archive_path


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestArchivePathTraversal:
    """SEC-BACK-001: Path traversal prevention."""

    def test_rejects_traversal_in_member_name(self, tmp_dir):
        archive = os.path.join(tmp_dir, "traversal.tar.zst")
        _create_tar_zst(archive, [
            {"name": "data/profile.db", "data": b"fake db"},
            {"name": "manifest.json", "data": b'{"test": true}'},
            {"name": "../etc/passwd", "data": b"root:x:0:0:"},
        ])
        result = verify_backup_package(archive)
        assert result["traversal_issues"] == ["../etc/passwd"]
        assert result["valid"] is False

    def test_rejects_nested_traversal(self, tmp_dir):
        archive = os.path.join(tmp_dir, "nested_traversal.tar.zst")
        _create_tar_zst(archive, [
            {"name": "data/profile.db", "data": b"fake db"},
            {"name": "manifest.json", "data": b'{"test": true}'},
            {"name": "cas/../../secrets.json", "data": b"secret"},
        ])
        result = verify_backup_package(archive)
        assert len(result["traversal_issues"]) > 0


class TestArchiveMemberValidation:
    """SEC-BACK-002: Only regular files allowed."""

    def test_valid_archive_passes(self, tmp_dir):
        archive = os.path.join(tmp_dir, "valid.tar.zst")
        _create_tar_zst(archive, [
            {"name": "data/profile.db", "data": b"fake db"},
            {"name": "manifest.json", "data": b'{"test": true}'},
        ])
        result = verify_backup_package(archive)
        assert result["valid"] is True
        assert result["manifest_found"] is True
        assert result["db_found"] is True


class TestSensitiveFileExclusion:
    """SEC-BACK-003: Sensitive file exclusion."""

    def test_sensitive_exclude_list_present(self):
        from ibreeze.backup.service import _SENSITIVE_FILES
        assert "secrets.json" in _SENSITIVE_FILES
        assert ".env" in _SENSITIVE_FILES
        assert "credentials.json" in _SENSITIVE_FILES
