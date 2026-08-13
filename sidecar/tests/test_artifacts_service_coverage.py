"""Coverage-focused tests for the artifact CAS service.

These tests exercise branches of ``ibreeze.artifacts.service`` that are not
covered by the existing artifact tests: the ``supersedes`` path (stale-review
side effects), content retrieval from CAS, manifest-backed creation, and the
dangling-chain break in version-chain traversal.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from ibreeze.artifacts.service import (
    create_artifact,
    create_artifact_with_manifest,
    get_artifact_content,
    get_artifact_version_chain,
)
from ibreeze.artifacts.storage import ArtifactStorage

_NOW = "2026-01-01T00:00:00.000000Z"


@pytest.fixture
def tmp_storage(tmp_path):
    return ArtifactStorage(base_path=str(tmp_path / "artifacts"))


@pytest.mark.asyncio
class TestCreateArtifactSupersedes:
    async def test_supersedes_marks_current_and_stales_reviews(self, db) -> None:
        await db.execute("PRAGMA foreign_keys = OFF")
        company_id = str(uuid.uuid4())

        base = await create_artifact(
            db,
            company_id,
            company_task_id="task-1",
            artifact_type="source_code_patch",
            content=b"v1 content",
            filename="a.py",
            mime_type="text/plain",
            created_by_employee_id="emp-1",
        )
        base_sha = base["content_sha256"]

        # Assignment that must transition to stale.
        await db.execute(
            """INSERT INTO review_assignments
               (id, company_id, artifact_id, reviewer_employee_id, review_round,
                reviewed_sha256, status, assigned_at)
               VALUES (?,?,?,?,1,?,'submitted',?)""",
            ("asgn-1", company_id, base["id"], "emp-1", base_sha, _NOW),
        )
        # Already-stale and cancelled assignments must not change.
        await db.execute(
            """INSERT INTO review_assignments
               (id, company_id, artifact_id, reviewer_employee_id, review_round,
                reviewed_sha256, status, assigned_at)
               VALUES (?,?,?,?,1,?,'stale',?)""",
            ("asgn-2", company_id, base["id"], "emp-2", base_sha, _NOW),
        )
        await db.execute(
            """INSERT INTO review_assignments
               (id, company_id, artifact_id, reviewer_employee_id, review_round,
                reviewed_sha256, status, assigned_at)
               VALUES (?,?,?,?,1,?,'cancelled',?)""",
            ("asgn-3", company_id, base["id"], "emp-3", base_sha, _NOW),
        )
        # Full review chain: report + issue that must be superseded.
        await db.execute(
            """INSERT INTO review_reports
               (id, company_id, assignment_id, reviewer_run_id, reviewed_artifact_id,
                reviewed_sha256, verdict, report_artifact_id, created_at)
               VALUES (?,?,?,?,?,?,'needs_changes',?,?)""",
            ("rep-1", company_id, "asgn-1", "run-1", base["id"], base_sha, "rep-art-1", _NOW),
        )
        await db.execute(
            """INSERT INTO review_issues
               (id, company_id, review_report_id, severity, category, description,
                expected, actual, suggested_fix, evidence_refs_json, status,
                assignee_employee_id, created_at, updated_at)
               VALUES (?,?,?,'high','code_quality','d','e','a','fix','[]','open',
                       NULL,?,?)""",
            ("iss-1", company_id, "rep-1", _NOW, _NOW),
        )

        result = await create_artifact(
            db,
            company_id,
            company_task_id="task-1",
            artifact_type="source_code_patch",
            content=b"v2 content",
            filename="a.py",
            mime_type="text/plain",
            created_by_employee_id="emp-1",
            supersedes_artifact_id=base["id"],
        )

        assert result["deduplicated"] is False
        assert result["superseded"] is True

        base_row = await (
            await db.execute(
                "SELECT is_current FROM artifacts WHERE id=? AND company_id=?",
                (base["id"], company_id),
            )
        ).fetchone()
        assert base_row["is_current"] == 0

        stale = await (await db.execute("SELECT status FROM review_assignments WHERE id='asgn-1'")).fetchone()
        assert stale["status"] == "stale"

        for assignment_id in ("asgn-2", "asgn-3"):
            row = await (
                await db.execute("SELECT status FROM review_assignments WHERE id=?", (assignment_id,))
            ).fetchone()
            assert row["status"] in ("stale", "cancelled")

        issue = await (await db.execute("SELECT superseded_by_artifact_id FROM review_issues WHERE id='iss-1'")).fetchone()
        assert issue["superseded_by_artifact_id"] == result["id"]

    async def test_supersedes_with_missing_old_artifact(self, db) -> None:
        await db.execute("PRAGMA foreign_keys = OFF")
        company_id = str(uuid.uuid4())

        result = await create_artifact(
            db,
            company_id,
            company_task_id="task-1",
            artifact_type="document",
            content=b"new content",
            filename="doc.md",
            mime_type="text/markdown",
            created_by_employee_id="emp-1",
            supersedes_artifact_id="missing-artifact-id",
        )
        assert result["superseded"] is True
        assert result["deduplicated"] is False
        assert "id" in result


@pytest.mark.asyncio
class TestArtifactVersionChainBreak:
    async def test_break_when_chain_references_missing_artifact(self, mock_db_session) -> None:
        # First node points at a nonexistent id; get_artifact returns None and the
        # traversal must break instead of looping forever.
        call_count = 0

        async def mock_execute(sql, params=()):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(
                    fetchone=AsyncMock(return_value={"id": "art-1", "supersedes_artifact_id": "missing-id"})
                )
            return MagicMock(fetchone=AsyncMock(return_value=None))

        mock_db_session.execute = mock_execute
        chain = await get_artifact_version_chain(mock_db_session, "comp-1", "art-1")
        assert [row["id"] for row in chain] == ["art-1"]


@pytest.mark.asyncio
class TestGetArtifactContent:
    async def test_returns_content_from_storage(self, db, monkeypatch, tmp_storage) -> None:
        await db.execute("PRAGMA foreign_keys = OFF")
        company_id = str(uuid.uuid4())
        payload = b"cas payload bytes"

        result = await create_artifact(
            db,
            company_id,
            company_task_id="task-1",
            artifact_type="log",
            content=payload,
            filename="run.log",
            mime_type="text/plain",
            created_by_employee_id="emp-1",
        )
        tmp_storage.write(payload)
        monkeypatch.setattr("ibreeze.artifacts.storage.get_storage", lambda: tmp_storage)

        content = await get_artifact_content(db, result["id"], company_id)
        assert content == payload

    async def test_returns_none_for_missing_artifact(self, db, monkeypatch, tmp_storage) -> None:
        monkeypatch.setattr("ibreeze.artifacts.storage.get_storage", lambda: tmp_storage)
        content = await get_artifact_content(db, "missing-id", "company-x")
        assert content is None


@pytest.mark.asyncio
class TestCreateArtifactWithManifest:
    async def test_create_manifest_normal(self, db, monkeypatch, tmp_storage) -> None:
        await db.execute("PRAGMA foreign_keys = OFF")
        monkeypatch.setattr("ibreeze.artifacts.storage.get_storage", lambda: tmp_storage)
        company_id = str(uuid.uuid4())

        result = await create_artifact_with_manifest(
            db,
            company_id=company_id,
            company_task_id="task-1",
            artifact_type="manifest",
            relative_path="releases/catalog.json",
            content=b'{"catalog":"v1"}',
            created_by_employee_id="emp-1",
        )
        assert result["deduplicated"] is False
        assert result["superseded"] is False
        assert "id" in result

    async def test_create_manifest_deduplicates(self, db, monkeypatch, tmp_storage) -> None:
        await db.execute("PRAGMA foreign_keys = OFF")
        monkeypatch.setattr("ibreeze.artifacts.storage.get_storage", lambda: tmp_storage)
        company_id = str(uuid.uuid4())

        first = await create_artifact_with_manifest(
            db,
            company_id=company_id,
            company_task_id="task-1",
            artifact_type="manifest",
            relative_path="releases/catalog.json",
            content=b'{"catalog":"v1"}',
            created_by_employee_id="emp-1",
        )
        second = await create_artifact_with_manifest(
            db,
            company_id=company_id,
            company_task_id="task-1",
            artifact_type="manifest",
            relative_path="releases/catalog.json",
            content=b'{"catalog":"v1"}',
            created_by_employee_id="emp-1",
        )
        assert second["deduplicated"] is True
        assert second["id"] == first["id"]

    async def test_create_manifest_supersedes(self, db, monkeypatch, tmp_storage) -> None:
        await db.execute("PRAGMA foreign_keys = OFF")
        monkeypatch.setattr("ibreeze.artifacts.storage.get_storage", lambda: tmp_storage)
        company_id = str(uuid.uuid4())

        base = await create_artifact(
            db,
            company_id,
            company_task_id="task-1",
            artifact_type="manifest",
            content=b"base manifest",
            filename="catalog.json",
            mime_type="application/json",
            created_by_employee_id="emp-1",
        )
        base_sha = base["content_sha256"]
        await db.execute(
            """INSERT INTO review_assignments
               (id, company_id, artifact_id, reviewer_employee_id, review_round,
                reviewed_sha256, status, assigned_at)
               VALUES (?,?,?,?,1,?,'submitted',?)""",
            ("asgn-m", company_id, base["id"], "emp-1", base_sha, _NOW),
        )
        await db.execute(
            """INSERT INTO review_reports
               (id, company_id, assignment_id, reviewer_run_id, reviewed_artifact_id,
                reviewed_sha256, verdict, report_artifact_id, created_at)
               VALUES (?,?,?,?,?,?,'needs_changes',?,?)""",
            ("rep-m", company_id, "asgn-m", "run-1", base["id"], base_sha, "rep-art-1", _NOW),
        )
        await db.execute(
            """INSERT INTO review_issues
               (id, company_id, review_report_id, severity, category, description,
                expected, actual, suggested_fix, evidence_refs_json, status,
                assignee_employee_id, created_at, updated_at)
               VALUES (?,?,?,'medium','code_quality','d','e','a','fix','[]','open',
                       NULL,?,?)""",
            ("iss-m", company_id, "rep-m", _NOW, _NOW),
        )

        result = await create_artifact_with_manifest(
            db,
            company_id=company_id,
            company_task_id="task-1",
            artifact_type="manifest",
            relative_path="releases/catalog.json",
            content=b"new manifest",
            created_by_employee_id="emp-1",
            supersedes_artifact_id=base["id"],
        )
        assert result["superseded"] is True

        base_row = await (
            await db.execute(
                "SELECT is_current FROM artifacts WHERE id=? AND company_id=?",
                (base["id"], company_id),
            )
        ).fetchone()
        assert base_row["is_current"] == 0

        stale = await (await db.execute("SELECT status FROM review_assignments WHERE id='asgn-m'")).fetchone()
        assert stale["status"] == "stale"

        issue = await (await db.execute("SELECT superseded_by_artifact_id FROM review_issues WHERE id='iss-m'")).fetchone()
        assert issue["superseded_by_artifact_id"] == result["id"]

    async def test_create_manifest_supersedes_missing_old(self, db, monkeypatch, tmp_storage) -> None:
        await db.execute("PRAGMA foreign_keys = OFF")
        monkeypatch.setattr("ibreeze.artifacts.storage.get_storage", lambda: tmp_storage)
        company_id = str(uuid.uuid4())

        result = await create_artifact_with_manifest(
            db,
            company_id=company_id,
            company_task_id="task-1",
            artifact_type="manifest",
            relative_path="releases/catalog.json",
            content=b"brand new manifest",
            created_by_employee_id="emp-1",
            supersedes_artifact_id="missing-artifact-id",
        )
        assert result["superseded"] is True
        assert result["deduplicated"] is False
