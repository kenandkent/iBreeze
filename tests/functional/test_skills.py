"""Skill ZIP validation and storage tests.

Covers design spec sections:
- G.8 Skill Management (ZIP validation, signing, storage)
"""
import hashlib
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# ZIP validation
# ---------------------------------------------------------------------------

class TestZipValidation:
    """ZIP structure validation for skill packages."""

    def test_valid_zip_structure(self, tmp_path):
        from ibreeze_backend.services.zip_service import validate_zip_structure

        zip_path = tmp_path / "valid.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", '{"name": "test"}')
            zf.writestr("skill.py", "print('hello')")

        valid, errors = validate_zip_structure(zip_path)
        assert valid is True
        assert errors == []

    def test_missing_manifest(self, tmp_path):
        from ibreeze_backend.services.zip_service import validate_zip_structure

        zip_path = tmp_path / "no_manifest.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("skill.py", "print('hello')")

        valid, errors = validate_zip_structure(zip_path)
        assert valid is False
        assert any("manifest.json" in e for e in errors)

    def test_no_python_files(self, tmp_path):
        from ibreeze_backend.services.zip_service import validate_zip_structure

        zip_path = tmp_path / "no_py.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", "{}")
            zf.writestr("readme.txt", "hello")

        valid, errors = validate_zip_structure(zip_path)
        assert valid is False
        assert any("Python" in e for e in errors)

    def test_suspicious_absolute_path(self, tmp_path):
        from ibreeze_backend.services.zip_service import validate_zip_structure

        zip_path = tmp_path / "bad_path.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", "{}")
            zf.writestr("skill.py", "ok")
            zf.writestr("/etc/passwd", "bad")

        valid, errors = validate_zip_structure(zip_path)
        assert valid is False
        assert any("Suspicious" in e for e in errors)

    def test_suspicious_traversal_path(self, tmp_path):
        from ibreeze_backend.services.zip_service import validate_zip_structure

        zip_path = tmp_path / "traversal.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", "{}")
            zf.writestr("skill.py", "ok")
            zf.writestr("../../../etc/passwd", "bad")

        valid, errors = validate_zip_structure(zip_path)
        assert valid is False
        assert any("Suspicious" in e for e in errors)

    def test_dangerous_exe_file(self, tmp_path):
        from ibreeze_backend.services.zip_service import validate_zip_structure

        zip_path = tmp_path / "exe.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", "{}")
            zf.writestr("skill.py", "ok")
            zf.writestr("malware.exe", "bad")

        valid, errors = validate_zip_structure(zip_path)
        assert valid is False
        assert any("dangerous" in e.lower() for e in errors)

    def test_dangerous_shell_script(self, tmp_path):
        from ibreeze_backend.services.zip_service import validate_zip_structure

        zip_path = tmp_path / "shell.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("manifest.json", "{}")
            zf.writestr("skill.py", "ok")
            zf.writestr("exploit.sh", "rm -rf /")

        valid, errors = validate_zip_structure(zip_path)
        assert valid is False
        assert any("dangerous" in e.lower() for e in errors)

    def test_invalid_zip_file(self, tmp_path):
        from ibreeze_backend.services.zip_service import validate_zip_structure

        zip_path = tmp_path / "corrupt.zip"
        zip_path.write_bytes(b"this is not a zip file")

        valid, errors = validate_zip_structure(zip_path)
        assert valid is False
        assert any("Invalid ZIP" in e for e in errors)

    def test_empty_zip(self, tmp_path):
        from ibreeze_backend.services.zip_service import validate_zip_structure

        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            pass  # Empty archive

        valid, errors = validate_zip_structure(zip_path)
        assert valid is False
        assert len(errors) >= 2  # Missing both manifest and .py


class TestZipChecksum:
    """ZIP file checksum computation."""

    def test_checksum_sha256(self, tmp_path):
        from ibreeze_backend.services.zip_service import compute_zip_checksum

        zip_path = tmp_path / "test.zip"
        zip_path.write_bytes(b"file content")

        checksum = compute_zip_checksum(zip_path)
        assert len(checksum) == 64  # SHA256 hex length
        assert checksum == hashlib.sha256(b"file content").hexdigest()

    def test_checksum_deterministic(self, tmp_path):
        from ibreeze_backend.services.zip_service import compute_zip_checksum

        zip_path = tmp_path / "test.zip"
        zip_path.write_bytes(b"same content")

        c1 = compute_zip_checksum(zip_path)
        c2 = compute_zip_checksum(zip_path)
        assert c1 == c2

    def test_checksum_different_for_different_content(self, tmp_path):
        from ibreeze_backend.services.zip_service import compute_zip_checksum

        p1 = tmp_path / "a.zip"
        p2 = tmp_path / "b.zip"
        p1.write_bytes(b"content A")
        p2.write_bytes(b"content B")

        assert compute_zip_checksum(p1) != compute_zip_checksum(p2)


class TestSignatureVerification:
    """ZIP signature verification (placeholder)."""

    def test_verify_signature_placeholder(self, tmp_path):
        from ibreeze_backend.services.zip_service import verify_signature

        zip_path = tmp_path / "test.zip"
        zip_path.write_bytes(b"data")
        # Currently placeholder always returns True
        assert verify_signature(zip_path, "sig", "key") is True


# ---------------------------------------------------------------------------
# Object storage
# ---------------------------------------------------------------------------

class TestObjectStorage:
    """Local filesystem object storage."""

    def test_store_and_retrieve(self, tmp_path):
        from ibreeze_backend.services.storage_service import ObjectStorage

        storage = ObjectStorage(base_path=tmp_path / "storage")
        source = tmp_path / "skill.zip"
        source.write_bytes(b"zip content")

        dest = storage.store("skill-1", "1.0.0", source)
        assert dest.exists()

        retrieved = storage.retrieve("skill-1", "1.0.0")
        assert retrieved is not None
        assert retrieved.exists()

    def test_retrieve_nonexistent(self, tmp_path):
        from ibreeze_backend.services.storage_service import ObjectStorage

        storage = ObjectStorage(base_path=tmp_path / "storage")
        assert storage.retrieve("nonexistent", "1.0.0") is None

    def test_delete_existing(self, tmp_path):
        from ibreeze_backend.services.storage_service import ObjectStorage

        storage = ObjectStorage(base_path=tmp_path / "storage")
        source = tmp_path / "skill.zip"
        source.write_bytes(b"data")
        storage.store("skill-1", "1.0.0", source)

        assert storage.delete("skill-1", "1.0.0") is True
        assert storage.retrieve("skill-1", "1.0.0") is None

    def test_delete_nonexistent(self, tmp_path):
        from ibreeze_backend.services.storage_service import ObjectStorage

        storage = ObjectStorage(base_path=tmp_path / "storage")
        assert storage.delete("nonexistent", "1.0.0") is False

    def test_list_versions(self, tmp_path):
        from ibreeze_backend.services.storage_service import ObjectStorage

        storage = ObjectStorage(base_path=tmp_path / "storage")
        source = tmp_path / "skill.zip"
        source.write_bytes(b"data")
        storage.store("skill-1", "1.0.0", source)
        storage.store("skill-1", "1.1.0", source)
        storage.store("skill-1", "2.0.0", source)

        versions = storage.list_versions("skill-1")
        assert versions == ["1.0.0", "1.1.0", "2.0.0"]

    def test_list_versions_empty(self, tmp_path):
        from ibreeze_backend.services.storage_service import ObjectStorage

        storage = ObjectStorage(base_path=tmp_path / "storage")
        assert storage.list_versions("nonexistent") == []

    def test_store_creates_directories(self, tmp_path):
        from ibreeze_backend.services.storage_service import ObjectStorage

        storage = ObjectStorage(base_path=tmp_path / "deep" / "nested" / "storage")
        source = tmp_path / "skill.zip"
        source.write_bytes(b"data")
        dest = storage.store("s1", "1.0.0", source)
        assert dest.exists()
