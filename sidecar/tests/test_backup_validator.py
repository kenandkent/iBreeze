"""Tests for backup restore validation.

Covers validate_backup_database, validate_backup_archive, restore_from_backup.
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import tarfile
from pathlib import Path

import pytest
import zstandard as zstd

from ibreeze.backup.validator import (
    restore_from_backup,
    validate_backup_archive,
    validate_backup_database,
)

REQUIRED_TABLE_NAMES = frozenset(
    {
        "companies",
        "departments",
        "employees",
        "conversations",
        "agent_runs",
        "artifacts",
        "knowledge_items",
        "backup_records",
        "domain_events",
        "schema_migrations",
        "embedding_generations",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_db(path: str, tables: dict[str, list[tuple]] | None = None):
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version = 1")
    if tables:
        for ddl, rows in tables.items():
            cursor.execute(ddl)
            for row in rows:
                placeholders = ",".join("?" for _ in row)
                cursor.execute(f"INSERT INTO {ddl.split()[2]} VALUES ({placeholders})", row)
    conn.commit()
    conn.close()


MIGRATIONS_DDL = "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT, applied_at TEXT, checksum TEXT)"


def _create_minimal_valid_db(path: str):
    conn = sqlite3.connect(path)
    for t in REQUIRED_TABLE_NAMES:
        ddl = MIGRATIONS_DDL if t == "schema_migrations" else f"CREATE TABLE {t} (id TEXT PRIMARY KEY)"
        conn.execute(ddl)
    conn.execute("INSERT INTO schema_migrations VALUES (1, 'init', '2024-01-01', 'abc')")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()


def _make_tar_zst_bytes(members: list[tuple[str, bytes]]) -> bytes:
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w|") as tar:
        for name, content in members:
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    raw_tar = tar_buf.getvalue()
    return zstd.ZstdCompressor().compress(raw_tar)


@pytest.fixture
def valid_db(tmp_path: Path) -> Path:
    db = tmp_path / "profile.db"
    _create_minimal_valid_db(str(db))
    return db


@pytest.fixture
def valid_archive(tmp_path: Path, valid_db: Path) -> Path:
    db_content = valid_db.read_bytes()
    manifest = json.dumps({"backup_id": "test"}).encode()
    data = _make_tar_zst_bytes(
        [
            ("manifest.json", manifest),
            ("data/profile.db", db_content),
        ]
    )
    archive = tmp_path / "backup.tar.zst"
    archive.write_bytes(data)
    return archive


# ===================================================================
# validate_backup_database
# ===================================================================


class TestValidateBackupDatabase:
    async def test_valid_database(self, valid_db: Path):
        result = await validate_backup_database(str(valid_db))
        assert result["valid"] is True
        assert result["errors"] == []
        assert isinstance(result["schema_version"], int)
        assert result["user_version"] == 1
        assert result["table_count"] == 11
        assert result["migration_count"] == 1
        assert result["migrations"][0]["version"] == 1
        assert result["fk_violation_count"] == 0
        assert result["ref_issues"] == []

    async def test_file_not_found(self):
        result = await validate_backup_database("/nonexistent/path.db")
        assert result["valid"] is False
        assert len(result["errors"]) == 1

    async def test_integrity_check_failure(self, tmp_path: Path):
        db = tmp_path / "corrupt.db"
        db.write_text("not a sqlite database")
        result = await validate_backup_database(str(db))
        assert result["valid"] is False
        assert len(result["errors"]) >= 1

    async def test_missing_required_tables(self, tmp_path: Path):
        db = tmp_path / "partial.db"
        _create_db(
            str(db),
            {
                "CREATE TABLE companies (id TEXT PRIMARY KEY)": [],
                "CREATE TABLE employees (id TEXT PRIMARY KEY)": [],
            },
        )
        result = await validate_backup_database(str(db))
        assert result["valid"] is False
        missing_errors = [e for e in result["errors"] if "Missing required tables" in e]
        assert len(missing_errors) == 1

    async def test_no_schema_migrations_table_is_error(self, tmp_path: Path):
        db = tmp_path / "no_migrations.db"
        conn = sqlite3.connect(str(db))
        for t in sorted(REQUIRED_TABLE_NAMES - {"schema_migrations"}):
            conn.execute(f"CREATE TABLE {t} (id TEXT PRIMARY KEY)")
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()
        result = await validate_backup_database(str(db))
        assert result["valid"] is False
        assert any("Missing required tables" in e for e in result["errors"])

    async def test_schema_migrations_table_empty(self, tmp_path: Path):
        db = tmp_path / "empty_migrations.db"
        conn = sqlite3.connect(str(db))
        for t in REQUIRED_TABLE_NAMES:
            ddl = MIGRATIONS_DDL if t == "schema_migrations" else f"CREATE TABLE {t} (id TEXT PRIMARY KEY)"
            conn.execute(ddl)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()
        result = await validate_backup_database(str(db))
        assert result["valid"] is True
        assert any("schema_migrations table is empty" in w for w in result["warnings"])
        assert result["migration_count"] == 0

    async def test_non_sequential_migrations(self, tmp_path: Path):
        db = tmp_path / "non_seq.db"
        _create_minimal_valid_db(str(db))
        conn = sqlite3.connect(str(db))
        conn.execute("INSERT INTO schema_migrations VALUES (3, 'v3', '2024-01-03', 'def')")
        conn.commit()
        conn.close()
        result = await validate_backup_database(str(db))
        assert result["valid"] is True
        assert any("Migration versions not sequential" in w for w in result["warnings"])

    async def test_fk_violations(self, tmp_path: Path):
        db = tmp_path / "fk_violations.db"
        conn = sqlite3.connect(str(db))
        for t in REQUIRED_TABLE_NAMES:
            ddl = MIGRATIONS_DDL if t == "schema_migrations" else f"CREATE TABLE {t} (id TEXT PRIMARY KEY)"
            conn.execute(ddl)
        conn.execute("INSERT INTO schema_migrations VALUES (1, 'init', '2024-01-01', 'abc')")
        conn.execute("CREATE TABLE child (id INTEGER PRIMARY KEY, pid INTEGER REFERENCES parent(id))")
        conn.execute("INSERT INTO child VALUES (1, 999)")
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()
        result = await validate_backup_database(str(db))
        assert result["valid"] is True
        assert result["fk_violation_count"] == 1
        assert result["fk_violations"][0]["table"] == "child"
        assert any("FK violations" in w for w in result["warnings"])

    async def test_orphaned_references(self, tmp_path: Path):
        db = tmp_path / "orphans.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE artifacts (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE knowledge_items (id TEXT PRIMARY KEY, source_artifact_id TEXT)")
        conn.execute("INSERT INTO knowledge_items VALUES ('k1', 'nonexistent-artifact')")
        conn.commit()
        conn.close()
        result = await validate_backup_database(str(db))
        assert result["valid"] is False
        assert any("Orphaned reference chains" in e for e in result["errors"])

    async def test_ref_chain_skips_missing_tables(self, tmp_path: Path):
        db = tmp_path / "partial_ref.db"
        _create_db(
            str(db),
            {
                "CREATE TABLE companies (id TEXT PRIMARY KEY)": [],
                "CREATE TABLE employees (id TEXT PRIMARY KEY, company_id TEXT)": [],
            },
        )
        result = await validate_backup_database(str(db))
        assert result["valid"] is False
        assert result["ref_issues"] == []

    async def test_no_orphans_when_refs_ok(self, valid_db: Path):
        result = await validate_backup_database(str(valid_db))
        assert result["ref_issues"] == []

    async def test_index_no_issues(self, valid_db: Path):
        result = await validate_backup_database(str(valid_db))
        index_warnings = [w for w in result["warnings"] if "Index issues" in w]
        assert len(index_warnings) == 0

    async def test_empty_database(self, tmp_path: Path):
        db = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db))
        conn.execute("PRAGMA user_version = 0")
        conn.commit()
        conn.close()
        result = await validate_backup_database(str(db))
        assert result["valid"] is False
        assert any("Missing required tables" in e for e in result["errors"])
        assert result["table_count"] == 0
        assert any("No schema_migrations table" in w for w in result["warnings"])

    async def test_db_with_extra_tables(self, tmp_path: Path):
        db = tmp_path / "extra.db"
        _create_minimal_valid_db(str(db))
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE extra_table (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        result = await validate_backup_database(str(db))
        assert result["valid"] is True
        assert result["table_count"] == 12

    async def test_user_version_custom(self, tmp_path: Path):
        db = tmp_path / "uv.db"
        _create_minimal_valid_db(str(db))
        conn = sqlite3.connect(str(db))
        conn.execute("PRAGMA user_version = 42")
        conn.commit()
        conn.close()
        result = await validate_backup_database(str(db))
        assert result["valid"] is True
        assert result["user_version"] == 42

    async def test_ref_chains_no_orphans(self, tmp_path: Path):
        db = tmp_path / "no_orphans.db"
        conn = sqlite3.connect(str(db))
        for t in REQUIRED_TABLE_NAMES:
            ddl = MIGRATIONS_DDL if t == "schema_migrations" else f"CREATE TABLE {t} (id TEXT PRIMARY KEY)"
            conn.execute(ddl)
        conn.execute("INSERT INTO schema_migrations VALUES (1, 'init', '2024-01-01', 'abc')")
        conn.execute("PRAGMA user_version = 1")
        conn.execute("CREATE TABLE conversation_messages (id TEXT PRIMARY KEY, source_event_id TEXT)")
        conn.execute("CREATE TABLE outbox_events (id TEXT PRIMARY KEY, domain_event_id TEXT)")
        conn.execute("ALTER TABLE knowledge_items ADD COLUMN source_artifact_id TEXT")
        conn.execute("ALTER TABLE knowledge_items ADD COLUMN source_message_event_id TEXT")
        conn.execute("ALTER TABLE embedding_generations ADD COLUMN company_id TEXT")
        conn.execute("INSERT INTO artifacts VALUES ('a1')")
        conn.execute("INSERT INTO domain_events VALUES ('e1')")
        conn.execute("INSERT INTO companies VALUES ('c1')")
        conn.execute(
            "INSERT INTO knowledge_items (id, source_artifact_id, source_message_event_id) VALUES ('k1', 'a1', 'e1')",
        )
        conn.execute("INSERT INTO embedding_generations (id, company_id) VALUES ('eg1', 'c1')")
        conn.commit()
        conn.close()
        result = await validate_backup_database(str(db))
        assert result["valid"] is True
        assert result["ref_issues"] == []

    async def test_integrity_check_returns_errors(self, tmp_path: Path):
        db = tmp_path / "corrupt_schema.db"
        _create_minimal_valid_db(str(db))
        raw = bytearray(db.read_bytes())
        raw[20] ^= 0xFF
        db.write_bytes(raw)
        result = await validate_backup_database(str(db))
        assert result["valid"] is False
        assert any("Integrity check failed" in e for e in result["errors"])


# ===================================================================
# validate_backup_archive
# ===================================================================


class TestValidateBackupArchive:
    async def test_archive_not_found(self):
        result = await validate_backup_archive("/nonexistent/archive.tar.zst")
        assert result["valid"] is False
        assert result["error"] == "Archive not found"

    async def test_valid_archive(self, valid_archive: Path):
        result = await validate_backup_archive(str(valid_archive))
        assert result["valid"] is True
        assert result["manifest_found"] is True
        assert result["db_found"] is True
        assert result["member_count"] == 2

    async def test_missing_manifest(self, tmp_path: Path, valid_db: Path):
        archive = tmp_path / "no_manifest.tar.zst"
        data = _make_tar_zst_bytes([("data/profile.db", valid_db.read_bytes())])
        archive.write_bytes(data)
        result = await validate_backup_archive(str(archive))
        assert result["valid"] is False
        assert result["error"] == "Manifest not found in archive"

    async def test_missing_database(self, tmp_path: Path):
        archive = tmp_path / "no_db.tar.zst"
        manifest = json.dumps({"backup_id": "test"}).encode()
        data = _make_tar_zst_bytes([("manifest.json", manifest)])
        archive.write_bytes(data)
        result = await validate_backup_archive(str(archive))
        assert result["valid"] is False
        assert result["error"] == "Database not found in archive"

    async def test_traversal_with_dotdot_prefix(self, tmp_path: Path):
        archive = tmp_path / "traversal1.tar.zst"
        manifest = json.dumps({"backup_id": "test"}).encode()
        data = _make_tar_zst_bytes(
            [
                ("manifest.json", manifest),
                ("data/profile.db", b"fake db"),
                ("../etc/passwd", b"evil"),
            ]
        )
        archive.write_bytes(data)
        result = await validate_backup_archive(str(archive))
        assert result["valid"] is True
        assert len(result["traversal_entries"]) == 1
        assert "../etc/passwd" in result["traversal_entries"]

    async def test_traversal_with_slash_dotdot(self, tmp_path: Path):
        archive = tmp_path / "traversal2.tar.zst"
        manifest = json.dumps({"backup_id": "test"}).encode()
        data = _make_tar_zst_bytes(
            [
                ("manifest.json", manifest),
                ("data/profile.db", b"fake db"),
                ("sub/../escape", b"evil"),
            ]
        )
        archive.write_bytes(data)
        result = await validate_backup_archive(str(archive))
        assert result["valid"] is True
        assert len(result["traversal_entries"]) == 1
        assert "sub/../escape" in result["traversal_entries"]

    async def test_multiple_traversal_entries(self, tmp_path: Path):
        archive = tmp_path / "traversal3.tar.zst"
        manifest = json.dumps({"backup_id": "test"}).encode()
        data = _make_tar_zst_bytes(
            [
                ("manifest.json", manifest),
                ("data/profile.db", b"fake db"),
                ("../etc/hosts", b"evil1"),
                ("a/../../../etc/shadow", b"evil2"),
            ]
        )
        archive.write_bytes(data)
        result = await validate_backup_archive(str(archive))
        assert result["valid"] is True
        assert len(result["traversal_entries"]) == 2

    async def test_no_traversal_in_normal_archive(self, valid_archive: Path):
        result = await validate_backup_archive(str(valid_archive))
        assert result["traversal_entries"] == []

    async def test_corrupted_archive(self, tmp_path: Path):
        archive = tmp_path / "corrupt.tar.zst"
        archive.write_bytes(b"not a valid zstd archive")
        result = await validate_backup_archive(str(archive))
        assert result["valid"] is False
        assert result["error"]

    async def test_empty_archive(self, tmp_path: Path):
        archive = tmp_path / "empty.tar.zst"
        data = _make_tar_zst_bytes([])
        archive.write_bytes(data)
        result = await validate_backup_archive(str(archive))
        assert result["valid"] is False
        assert result["error"] == "Manifest not found in archive"

    async def test_archive_with_multiple_members(self, valid_archive: Path, valid_db: Path):
        archive = valid_archive.parent / "multi.tar.zst"
        manifest = json.dumps({"backup_id": "test"}).encode()
        db_content = valid_db.read_bytes()
        data = _make_tar_zst_bytes(
            [
                ("manifest.json", manifest),
                ("data/profile.db", db_content),
                ("data/extra.txt", b"extra content"),
                ("data/extra2.txt", b"more content"),
            ]
        )
        archive.write_bytes(data)
        result = await validate_backup_archive(str(archive))
        assert result["valid"] is True
        assert result["member_count"] == 4


# ===================================================================
# restore_from_backup
# ===================================================================


class TestRestoreFromBackup:
    async def test_successful_restore(self, valid_archive: Path):
        target = valid_archive.parent / "restored.db"
        result = await restore_from_backup(str(target), str(valid_archive))
        assert result["success"] is True
        assert "restored_at" in result
        assert result["db_validation"]["valid"] is True
        assert os.path.exists(str(target))
        conn = sqlite3.connect(str(target))
        row = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()
        conn.close()
        assert row[0] == 1

    async def test_restore_with_staging_dir(self, valid_archive: Path, tmp_path: Path):
        target = tmp_path / "restored.db"
        staging = tmp_path / "my_staging"
        result = await restore_from_backup(str(target), str(valid_archive), staging_dir=str(staging))
        assert result["success"] is True
        assert os.path.exists(str(target))

    async def test_restore_overwrites_existing_db(self, valid_archive: Path):
        target = valid_archive.parent / "existing.db"
        target.write_text("old data")
        result = await restore_from_backup(str(target), str(valid_archive))
        assert result["success"] is True
        conn = sqlite3.connect(str(target))
        row = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()
        conn.close()
        assert row[0] == 1
        backup_files = list(valid_archive.parent.glob("existing.db.restore-before-*"))
        assert len(backup_files) == 1

    async def test_restore_archive_not_found(self, tmp_path: Path):
        result = await restore_from_backup(
            str(tmp_path / "target.db"),
            str(tmp_path / "nonexistent.tar.zst"),
        )
        assert result["success"] is False
        assert "Archive not found" in result["errors"][0]

    async def test_restore_invalid_archive(self, tmp_path: Path):
        archive = tmp_path / "bad.tar.zst"
        archive.write_bytes(b"garbage")
        result = await restore_from_backup(
            str(tmp_path / "target.db"),
            str(archive),
        )
        assert result["success"] is False
        assert len(result["errors"]) == 1

    async def test_restore_db_validation_fails(self, tmp_path: Path):
        db_with_issues = tmp_path / "bad_profile.db"
        conn = sqlite3.connect(str(db_with_issues))
        conn.execute("CREATE TABLE companies (id TEXT PRIMARY KEY)")
        conn.commit()
        conn.close()
        data = _make_tar_zst_bytes(
            [
                ("manifest.json", json.dumps({"backup_id": "test"}).encode()),
                ("data/profile.db", db_with_issues.read_bytes()),
            ]
        )
        archive = tmp_path / "bad_db_archive.tar.zst"
        archive.write_bytes(data)
        result = await restore_from_backup(
            str(tmp_path / "target.db"),
            str(archive),
        )
        assert result["success"] is False
        assert len(result["errors"]) > 0

    async def test_restore_no_migrations(self, tmp_path: Path):
        db_no_mig = tmp_path / "no_mig_profile.db"
        conn = sqlite3.connect(str(db_no_mig))
        for t in REQUIRED_TABLE_NAMES:
            ddl = MIGRATIONS_DDL if t == "schema_migrations" else f"CREATE TABLE {t} (id TEXT PRIMARY KEY)"
            conn.execute(ddl)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()
        data = _make_tar_zst_bytes(
            [
                ("manifest.json", json.dumps({"backup_id": "test"}).encode()),
                ("data/profile.db", db_no_mig.read_bytes()),
            ]
        )
        archive = tmp_path / "no_mig_archive.tar.zst"
        archive.write_bytes(data)
        result = await restore_from_backup(
            str(tmp_path / "target.db"),
            str(archive),
        )
        assert result["success"] is False
        assert "Schema has no migrations applied" in result["errors"][0]

    async def test_restore_incomplete_migration_chain(self, tmp_path: Path):
        db_incomplete = tmp_path / "incomplete_profile.db"
        _create_minimal_valid_db(str(db_incomplete))
        conn = sqlite3.connect(str(db_incomplete))
        conn.execute("INSERT OR IGNORE INTO schema_migrations VALUES (3, 'v3', '2024-01-03', 'def')")
        conn.commit()
        conn.close()
        data = _make_tar_zst_bytes(
            [
                ("manifest.json", json.dumps({"backup_id": "test"}).encode()),
                ("data/profile.db", db_incomplete.read_bytes()),
            ]
        )
        archive = tmp_path / "incomplete_archive.tar.zst"
        archive.write_bytes(data)
        result = await restore_from_backup(
            str(tmp_path / "target.db"),
            str(archive),
        )
        assert result["success"] is False
        assert "Migration chain incomplete" in result["errors"][0]

    async def test_restore_with_truncated_db(self, tmp_path: Path):
        db = tmp_path / "profile.db"
        _create_minimal_valid_db(str(db))
        original = db.read_bytes()
        db_content = original[: len(original) // 2]
        data = _make_tar_zst_bytes(
            [
                ("manifest.json", json.dumps({"backup_id": "test"}).encode()),
                ("data/profile.db", db_content),
            ]
        )
        archive = tmp_path / "truncated.tar.zst"
        archive.write_bytes(data)
        target = tmp_path / "target.db"
        staging = tmp_path / "my_staging"
        result = await restore_from_backup(
            str(target),
            str(archive),
            staging_dir=str(staging),
        )
        assert result["success"] is False
        assert len(result["errors"]) > 0

    async def test_staging_cleanup_after_failure(self, tmp_path: Path):
        archive = tmp_path / "cleanup_test.tar.zst"
        archive.write_bytes(b"garbage")
        target = tmp_path / "target.db"
        staging = tmp_path / "my_staging"
        result = await restore_from_backup(
            str(target),
            str(archive),
            staging_dir=str(staging),
        )
        assert result["success"] is False
        staging_path = os.path.join(str(staging), "restore_staging")
        assert not os.path.exists(staging_path)

    async def test_restore_creates_staging_and_cleans_up(self, valid_archive: Path):
        target = valid_archive.parent / "clean_target.db"
        staging = valid_archive.parent.parent / "restore_staging_custom"
        result = await restore_from_backup(
            str(target),
            str(valid_archive),
            staging_dir=str(staging),
        )
        assert result["success"] is True
        staging_path = os.path.join(str(staging), "restore_staging")
        assert not os.path.exists(staging_path)

    async def test_restore_exception_during_rename(self, tmp_path: Path, valid_db: Path):
        db_content = valid_db.read_bytes()
        data = _make_tar_zst_bytes(
            [
                ("manifest.json", json.dumps({"backup_id": "test"}).encode()),
                ("data/profile.db", db_content),
            ]
        )
        archive = tmp_path / "rename_fail.tar.zst"
        archive.write_bytes(data)
        parent_file = tmp_path / "not_a_dir"
        parent_file.write_text("i am a file, not a directory")
        target = parent_file / "target.db"
        staging = tmp_path / "my_staging"
        result = await restore_from_backup(
            str(target),
            str(archive),
            staging_dir=str(staging),
        )
        assert result["success"] is False
        assert len(result["errors"]) == 1

    async def test_restore_extracted_db_not_found(self, tmp_path: Path):
        manifest = json.dumps({"backup_id": "test"}).encode()
        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w|") as tar:
            mi = tarfile.TarInfo(name="manifest.json")
            mi.size = len(manifest)
            tar.addfile(mi, io.BytesIO(manifest))
            li = tarfile.TarInfo(name="data/profile.db")
            li.type = tarfile.SYMTYPE
            li.linkname = "../nonexistent"
            tar.addfile(li)
        raw = tar_buf.getvalue()
        compressed = zstd.ZstdCompressor().compress(raw)
        archive = tmp_path / "symlink_db.tar.zst"
        archive.write_bytes(compressed)
        result = await restore_from_backup(
            str(tmp_path / "target.db"),
            str(archive),
            staging_dir=str(tmp_path / "staging"),
        )
        assert result["success"] is False
        assert "Database not found in extracted archive" in result["errors"][0]
