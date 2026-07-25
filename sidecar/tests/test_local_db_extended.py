"""Extended tests for ibreeze.local_db - CRUD, batch, read pool."""

from __future__ import annotations

import uuid

import pytest

from ibreeze.local_db import LocalDB

BACKUP_COLS = (
    "id, backup_type, archive_path, archive_size, "
    "archive_sha256, manifest_json, status, created_at"
)
BACKUP_INS = (
    "INSERT INTO backup_records "
    f"({BACKUP_COLS}) VALUES (?, 'manual', ?, 1, ?, '{{}}', 'creating', ?)"
)
NOW = "2026-01-01T00:00:00Z"
SHA = "a" * 64

_seq = 0


def _unique_path() -> str:
    global _seq
    _seq += 1
    return f"/p{_seq}"


def _backup_row(rid: str | None = None, path: str | None = None) -> tuple:
    return (rid or uuid.uuid4().hex, path or _unique_path(), SHA, NOW)


@pytest.mark.asyncio
async def test_execute_write_and_fetch(local_db: LocalDB) -> None:
    await local_db.execute_write(BACKUP_INS, _backup_row())
    row = await local_db.fetch_one("SELECT * FROM backup_records LIMIT 1")
    assert row is not None
    assert row["backup_type"] == "manual"


@pytest.mark.asyncio
async def test_fetch_val(local_db: LocalDB) -> None:
    assert await local_db.fetch_val("SELECT 42") == 42


@pytest.mark.asyncio
async def test_fetch_val_empty(local_db: LocalDB) -> None:
    assert await local_db.fetch_val("SELECT 1 WHERE 1=0") is None


@pytest.mark.asyncio
async def test_fetch_all(local_db: LocalDB) -> None:
    rows = await local_db.fetch_all("SELECT 1 AS v UNION ALL SELECT 2")
    assert len(rows) == 2
    assert rows[0]["v"] == 1


@pytest.mark.asyncio
async def test_execute_many_write(local_db: LocalDB) -> None:
    ids = [uuid.uuid4().hex for _ in range(3)]
    await local_db.execute_many_write(BACKUP_INS, [_backup_row(i) for i in ids])
    count = await local_db.fetch_val("SELECT COUNT(*) FROM backup_records")
    assert count == 3


@pytest.mark.asyncio
async def test_execute_write_batch(local_db: LocalDB) -> None:
    id1, id2 = uuid.uuid4().hex, uuid.uuid4().hex
    results = await local_db.execute_write_batch([
        (BACKUP_INS, _backup_row(id1)),
        (BACKUP_INS, _backup_row(id2)),
    ])
    assert len(results) == 2
    assert await local_db.fetch_val("SELECT COUNT(*) FROM backup_records") == 2


@pytest.mark.asyncio
async def test_insert_and_get_by_id(local_db: LocalDB) -> None:
    rid = uuid.uuid4().hex
    data = {
        "id": rid, "backup_type": "manual", "archive_path": _unique_path(),
        "archive_size": 10, "archive_sha256": SHA, "manifest_json": "{}",
        "status": "creating", "created_at": NOW,
    }
    await local_db.insert("backup_records", data)
    row = await local_db.get_by_id("backup_records", rid)
    assert row is not None
    assert row["id"] == rid


@pytest.mark.asyncio
async def test_get_by_id_not_found(local_db: LocalDB) -> None:
    assert await local_db.get_by_id("backup_records", "nosuch") is None


@pytest.mark.asyncio
async def test_update_by_id(local_db: LocalDB) -> None:
    rid = uuid.uuid4().hex
    await local_db.insert("backup_records", {
        "id": rid, "backup_type": "manual", "archive_path": _unique_path(),
        "archive_size": 1, "archive_sha256": SHA, "manifest_json": "{}",
        "status": "creating", "created_at": NOW,
    })
    updated = await local_db.update_by_id("backup_records", rid, {"status": "completed"})
    assert updated["status"] == "completed"


@pytest.mark.asyncio
async def test_update_by_id_empty_data(local_db: LocalDB) -> None:
    rid = uuid.uuid4().hex
    await local_db.insert("backup_records", {
        "id": rid, "backup_type": "manual", "archive_path": _unique_path(),
        "archive_size": 1, "archive_sha256": SHA, "manifest_json": "{}",
        "status": "creating", "created_at": NOW,
    })
    result = await local_db.update_by_id("backup_records", rid, {})
    assert result["id"] == rid


@pytest.mark.asyncio
async def test_delete_by_id(local_db: LocalDB) -> None:
    rid = uuid.uuid4().hex
    await local_db.insert("backup_records", {
        "id": rid, "backup_type": "manual", "archive_path": _unique_path(),
        "archive_size": 1, "archive_sha256": SHA, "manifest_json": "{}",
        "status": "creating", "created_at": NOW,
    })
    assert await local_db.delete_by_id("backup_records", rid) is True
    assert await local_db.get_by_id("backup_records", rid) is None


@pytest.mark.asyncio
async def test_delete_by_id_not_found(local_db: LocalDB) -> None:
    assert await local_db.delete_by_id("backup_records", "nonexistent") is False


@pytest.mark.asyncio
async def test_list_all(local_db: LocalDB) -> None:
    for i in range(5):
        await local_db.insert("backup_records", {
            "id": uuid.uuid4().hex, "backup_type": "manual",
            "archive_path": _unique_path(), "archive_size": i + 1,
            "archive_sha256": SHA, "manifest_json": "{}",
            "status": "creating", "created_at": NOW,
        })
    rows = await local_db.list_all("backup_records", limit=3)
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_list_all_with_filters(local_db: LocalDB) -> None:
    await local_db.insert("backup_records", {
        "id": uuid.uuid4().hex, "backup_type": "daily",
        "archive_path": _unique_path(), "archive_size": 1,
        "archive_sha256": SHA, "manifest_json": "{}",
        "status": "creating", "created_at": NOW,
    })
    rows = await local_db.list_all("backup_records", filters={"backup_type": "daily"})
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_count(local_db: LocalDB) -> None:
    for i in range(3):
        await local_db.insert("backup_records", {
            "id": uuid.uuid4().hex, "backup_type": "manual",
            "archive_path": _unique_path(), "archive_size": i + 1,
            "archive_sha256": SHA, "manifest_json": "{}",
            "status": "creating", "created_at": NOW,
        })
    assert await local_db.count("backup_records") == 3
    assert await local_db.count("backup_records", filters={"backup_type": "manual"}) == 3
    assert await local_db.count("backup_records", filters={"backup_type": "nope"}) == 0


@pytest.mark.asyncio
async def test_write_connection_and_db_path(local_db: LocalDB) -> None:
    assert local_db.write_connection is not None
    assert local_db.db_path.suffix == ".db"


@pytest.mark.asyncio
async def test_execute_script(local_db: LocalDB) -> None:
    sha2 = "b" * 64
    await local_db.execute_script(
        f"INSERT INTO backup_records ({BACKUP_COLS}) "
        f"VALUES ('s1', 'manual', '/scr1', 1, '{sha2}', '{{}}', 'creating', '{NOW}');"
        f"INSERT INTO backup_records ({BACKUP_COLS}) "
        f"VALUES ('s2', 'manual', '/scr2', 2, '{sha2}', '{{}}', 'creating', '{NOW}');"
    )
    assert await local_db.fetch_val("SELECT COUNT(*) FROM backup_records") == 2


@pytest.mark.asyncio
async def test_execute_write_batch_rollback(local_db: LocalDB) -> None:
    with pytest.raises(Exception):
        await local_db.execute_write_batch([
            (BACKUP_INS, _backup_row()),
            ("INSERT INTO backup_records (id) VALUES ('bad')", ()),
        ])
    assert await local_db.fetch_val("SELECT COUNT(*) FROM backup_records") == 0


@pytest.mark.asyncio
async def test_read_pool_acquire_release(local_db: LocalDB) -> None:
    conn = await local_db._acquire_read()
    assert conn is not None
    await local_db._release_read(conn)


@pytest.mark.asyncio
async def test_list_all_offset(local_db: LocalDB) -> None:
    for i in range(5):
        await local_db.insert("backup_records", {
            "id": uuid.uuid4().hex, "backup_type": "manual",
            "archive_path": _unique_path(), "archive_size": i + 1,
            "archive_sha256": SHA, "manifest_json": "{}",
            "status": "creating", "created_at": NOW,
        })
    rows = await local_db.list_all("backup_records", limit=2, offset=2)
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_fetch_one_with_params(local_db: LocalDB) -> None:
    rid = uuid.uuid4().hex
    await local_db.execute_write(BACKUP_INS, _backup_row(rid))
    row = await local_db.fetch_one("SELECT * FROM backup_records WHERE id = ?", (rid,))
    assert row is not None
    assert row["id"] == rid


@pytest.mark.asyncio
async def test_list_all_no_filters(local_db: LocalDB) -> None:
    await local_db.insert("backup_records", {
        "id": uuid.uuid4().hex, "backup_type": "manual",
        "archive_path": _unique_path(), "archive_size": 1,
        "archive_sha256": SHA, "manifest_json": "{}",
        "status": "creating", "created_at": NOW,
    })
    rows = await local_db.list_all("backup_records")
    assert len(rows) == 1
