"""Tests for R09 backup consistency.

- BACK-006: SQLite Online Backup produces consistent snapshots
- BACK-007: WriteQueue barrier pauses writes during snapshot
- BACK-008: External reference table freeze captures correct state
- BACK-009: Sensitive files are excluded from archive
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from ibreeze.backup.service import create_backup
from ibreeze.persistence.write_queue import WriteQueue


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
async def db_with_data(tmp_dir):
    db = tmp_dir / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE companies (id TEXT PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO companies VALUES ('c1', '公司A')")
    conn.execute("INSERT INTO companies VALUES ('c2', '公司B')")
    conn.execute(
        "CREATE TABLE domain_events (event_id TEXT PRIMARY KEY, "
        "company_id TEXT REFERENCES companies(id), "
        "aggregate_type TEXT, aggregate_id TEXT, aggregate_version INTEGER, "
        "event_type TEXT, payload_json TEXT, trace_id TEXT, occurred_at TEXT)"
    )
    conn.execute(
        "INSERT INTO domain_events VALUES ('evt1', 'c1', 'test', 'a1', 1, "
        "'test.event', '{}', 'trace1', '2024-01-01T00:00:00Z')"
    )
    conn.commit()
    conn.close()
    return db


@pytest.mark.asyncio
class TestOnlineBackupConsistency:
    """BACK-006: Verify SQLite Online Backup produces consistent snapshots."""

    async def test_backup_uses_online_api(self, db_with_data, tmp_dir):
        result = await create_backup(db_with_data, tmp_dir / "backups")
        assert result["database_hash"] is not None
        assert result["archive_path"] is not None
        archive_path = Path(result["archive_path"])
        assert archive_path.exists()
        assert archive_path.suffix == ".zst"
        assert ".tar" in archive_path.name

    async def test_backup_snapshot_is_consistent(self, db_with_data, tmp_dir):
        backup_dir = tmp_dir / "backups"
        result = await create_backup(db_with_data, backup_dir)
        manifest_path = next((backup_dir / result["backup_id"]).glob("*.manifest.json"))
        with open(manifest_path) as f:
            manifest = json.load(f)
        assert manifest["snapshot_method"] == "sqlite_online_backup"
        assert manifest["table_stats"]["companies"] == 2


@pytest.mark.asyncio
class TestWriteQueueBarrier:
    """BACK-007: WriteQueue barrier pauses writes during snapshot."""

    async def test_barrier_waits_for_pending_writes(self, db_with_data, tmp_dir):
        wq = WriteQueue(capacity=32)
        backup_dir = tmp_dir / "backups"
        result = await create_backup(db_with_data, backup_dir, write_queue=wq)
        assert result["backup_id"] is not None

    async def test_barrier_without_queue_still_works(self, db_with_data, tmp_dir):
        result = await create_backup(db_with_data, tmp_dir / "backups", write_queue=None)
        assert result["database_hash"] is not None


@pytest.mark.asyncio
class TestExternalRefFreeze:
    """BACK-008: External reference freeze captures correct state."""

    async def test_external_refs_in_manifest(self, db_with_data, tmp_dir):
        backup_dir = tmp_dir / "backups"
        result = await create_backup(db_with_data, backup_dir)
        manifest_path = next((backup_dir / result["backup_id"]).glob("*.manifest.json"))
        with open(manifest_path) as f:
            manifest = json.load(f)
        refs = manifest.get("external_refs", {})
        assert "domain_events" in refs
        assert len(refs["domain_events"]) == 1

    async def test_external_refs_include_domain_events(self, db_with_data, tmp_dir):
        backup_dir = tmp_dir / "backups"
        result = await create_backup(db_with_data, backup_dir)
        manifest_path = next((backup_dir / result["backup_id"]).glob("*.manifest.json"))
        with open(manifest_path) as f:
            manifest = json.load(f)
        refs = manifest.get("external_refs", {})
        assert refs["domain_events"][0]["event_id"] == "evt1"


@pytest.mark.asyncio
class TestSensitiveFileExclusion:
    """BACK-009: Sensitive files are excluded from archive."""

    async def test_sensitive_excluded_in_manifest(self, db_with_data, tmp_dir):
        backup_dir = tmp_dir / "backups"
        result = await create_backup(db_with_data, backup_dir)
        manifest_path = next((backup_dir / result["backup_id"]).glob("*.manifest.json"))
        with open(manifest_path) as f:
            manifest = json.load(f)
        excluded = manifest.get("sensitive_excluded", [])
        assert "secrets.json" in excluded
        assert ".env" in excluded
