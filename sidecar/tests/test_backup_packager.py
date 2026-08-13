from __future__ import annotations

import hashlib
import os
from pathlib import Path

from ibreeze.backup.packager import (
    _safe_arcname,
    _sha256_file,
    _tar_filter,
    create_backup_package,
    verify_backup_package,
)


def test_sha256_file(tmp_path: Path):
    f = tmp_path / "test.txt"
    f.write_text("hello world")
    expected = hashlib.sha256(b"hello world").hexdigest()
    assert _sha256_file(f) == expected


def test_safe_arcname_resolves_relative():
    base = Path("/tmp/base")
    abs_path = Path("/tmp/base/sub/file.txt")
    result = _safe_arcname(base, abs_path)
    assert result == "sub/file.txt"


def test_safe_arcname_detects_traversal(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    abs_path = tmp_path / "outside" / "file.txt"
    abs_path.parent.mkdir(exist_ok=True)
    try:
        _safe_arcname(base, abs_path)
        assert False, "should have raised"
    except ValueError:
        pass


def test_tar_filter_keeps_regular_file():
    import tarfile

    info = tarfile.TarInfo(name="test.txt")
    info.type = tarfile.REGTYPE
    assert _tar_filter(info) is info


def test_tar_filter_keeps_directory():
    import tarfile

    info = tarfile.TarInfo(name="dir/")
    info.type = tarfile.DIRTYPE
    assert _tar_filter(info) is info


def test_tar_filter_rejects_symlink():
    import tarfile

    info = tarfile.TarInfo(name="link")
    info.type = tarfile.SYMTYPE
    assert _tar_filter(info) is None


class TestCreateBackupPackage:
    def test_creates_archive(self, tmp_path: Path):
        db_file = tmp_path / "profile.db"
        db_file.write_text("test db content")
        cas_dir = tmp_path / "cas"
        cas_dir.mkdir()
        (cas_dir / "file1.txt").write_text("cas content")

        output_dir = tmp_path / "backups"
        output_dir.mkdir()

        result = create_backup_package(str(db_file), str(cas_dir), str(output_dir), backup_type="manual")
        assert os.path.exists(result["archive_path"])
        assert result["archive_sha256"]
        assert result["archive_size"] > 0
        assert result["file_count"] >= 2

    def test_package_contains_manifest(self, tmp_path: Path):
        db_file = tmp_path / "profile.db"
        db_file.write_text("test")
        output_dir = tmp_path / "backups"
        output_dir.mkdir()

        result = create_backup_package(str(db_file), str(tmp_path / "empty_cas"), str(output_dir))

        import tarfile

        import zstandard as zstd

        with open(result["archive_path"], "rb") as f:
            dctx = zstd.ZstdDecompressor()
            with dctx.stream_reader(f) as reader:
                with tarfile.open(fileobj=reader, mode="r|") as tar:
                    names = [m.name for m in tar]
                    assert "manifest.json" in names

    def test_empty_cas(self, tmp_path: Path):
        db_file = tmp_path / "profile.db"
        db_file.write_text("test")
        cas_dir = tmp_path / "empty_cas"
        cas_dir.mkdir()
        output_dir = tmp_path / "backups"
        output_dir.mkdir()

        result = create_backup_package(str(db_file), str(cas_dir), str(output_dir))
        assert result["file_count"] == 1

    def test_missing_db_path(self, tmp_path: Path):
        output_dir = tmp_path / "backups"
        output_dir.mkdir()
        missing_db = tmp_path / "nonexistent.db"
        cas_dir = tmp_path / "empty_cas"
        cas_dir.mkdir()

        result = create_backup_package(str(missing_db), str(cas_dir), str(output_dir))
        assert os.path.exists(result["archive_path"])


class TestVerifyBackupPackage:
    def test_returns_error_when_not_found(self):
        result = verify_backup_package("/nonexistent/archive.tar.zst")
        assert result["valid"] is False
        assert "Archive not found" in result.get("error", "")

    def test_verifies_valid_archive(self, tmp_path: Path):
        db_file = tmp_path / "profile.db"
        db_file.write_text("test")
        output_dir = tmp_path / "backups"
        output_dir.mkdir()
        pkg_result = create_backup_package(str(db_file), str(tmp_path / "cas"), str(output_dir))
        result = verify_backup_package(pkg_result["archive_path"])
        assert result["valid"] is True
        assert result["manifest_found"] is True
        assert result["db_found"] is True
