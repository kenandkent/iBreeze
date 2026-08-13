"""Coverage for small leaf modules: artifacts.manifest, runtime.event_normalizer,
knowledge.generation, security.skill_verify and the assets package.

These modules are pure logic or thin DB helpers; a few direct tests push them
to ~100% and cheaply close the overall coverage gap.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ibreeze.artifacts.manifest import Manifest, ManifestEntry
from ibreeze.assets import get_asset_path, list_assets
from ibreeze.knowledge.generation import (
    count_items_for_generation,
    count_lancedb_items,
    count_lancedb_items_for_generation,
    get_active_generation,
    list_generations,
)
from ibreeze.runtime.event_normalizer import (
    EVENT_TYPES,
    create_approval_event,
    create_checkpoint,
    create_compacted_event,
    create_model_delta,
    create_model_done,
    create_run_cancelled,
    create_run_completed,
    create_run_failed,
    create_run_started,
    create_tool_approved_event,
    create_tool_event,
    create_tool_rejected_event,
    create_verification_completed_event,
    create_verification_started_event,
    create_workspace_changed_event,
    normalize_event,
    store_event,
)
from ibreeze.security.skill_verify import (
    SkillVerificationError,
    compute_package_hash,
    validate_package_paths,
    verify_skill_signature,
)


class TestManifest:
    def test_entry_defaults_and_to_dict(self) -> None:
        entry = ManifestEntry(relative_path="a/b.txt", action="create", after_sha256="x")
        data = entry.to_dict()
        assert data["relative_path"] == "a/b.txt"
        assert data["action"] == "create"
        assert data["before_sha256"] is None
        assert data["after_sha256"] == "x"
        assert data["mode"] == 0o644
        assert data["size_bytes"] == 0

    def test_manifest_roundtrip_and_hash(self) -> None:
        m = Manifest()
        m.add_create("new.txt", after_sha256="c1", size_bytes=3, mode=0o600)
        m.add_modify("edit.txt", before_sha256="b1", after_sha256="b2", size_bytes=9)
        m.add_delete("gone.txt", before_sha256="d1")
        raw = m.to_json()
        parsed = json.loads(raw)
        assert [e["action"] for e in parsed] == ["create", "modify", "delete"]
        restored = Manifest.from_json(raw)
        assert [e.relative_path for e in restored.entries] == ["new.txt", "edit.txt", "gone.txt"]
        assert restored.entries[1].before_sha256 == "b1"
        digest = m.compute_manifest_hash()
        assert len(digest) == 64
        assert hashlib.sha256(m.to_json().encode()).hexdigest() == digest


class TestEventNormalizer:
    def test_normalize_event_shape(self) -> None:
        event = normalize_event({"type": "run.started", "data": {"k": "v"}}, "run-1", 7)
        assert event["run_id"] == "run-1"
        assert event["sequence"] == 7
        assert event["event_type"] == "run.started"
        assert json.loads(event["payload_json"]) == {"k": "v"}
        assert event["trace_id"]

    def test_trace_id_passthrough(self) -> None:
        event = normalize_event({"type": "x", "data": {}}, "r", 1, trace_id="t-1")
        assert event["trace_id"] == "t-1"

    def test_event_type_catalog(self) -> None:
        assert len(EVENT_TYPES) == 14

    def test_create_helpers(self) -> None:
        started = create_run_started("r", 1, employee_id="e", model_id="m")
        assert started["event_type"] == "run.started"
        assert json.loads(started["payload_json"]) == {"employee_id": "e", "model_id": "m"}
        assert create_run_completed("r", 2, summary="s")["event_type"] == "run.completed"
        assert create_run_failed("r", 3, error="boom")["event_type"] == "run.failed"
        assert create_run_cancelled("r", 4)["event_type"] == "run.cancelled"
        assert create_model_delta("r", 5, delta="d")["event_type"] == "model.output.delta"
        assert create_model_done("r", 6, output="o")["event_type"] == "model.output.done"

    def test_tool_checkpoint_approval_helpers(self) -> None:
        for status in ("requested", "started", "completed", "failed"):
            ev = create_tool_event("r", 1, tool_name="bash", status=status, result=3)
            assert ev["event_type"] == f"tool.{status}"
            assert json.loads(ev["payload_json"]) == {"tool": "bash", "result": 3}
        assert create_checkpoint("r", 2, checkpoint_id="c")["event_type"] == "checkpoint.created"
        assert create_checkpoint("r", 3, checkpoint_id="c", restored=True)["event_type"] == "checkpoint.restored"
        assert create_approval_event("r", 4, tool_name="t", status="requested")["event_type"] == "approval.requested"
        assert create_approval_event("r", 5, tool_name="t", status="resolved")["event_type"] == "approval.resolved"
        with pytest.raises(ValueError, match="Invalid tool status"):
            create_tool_event("r", 6, tool_name="t", status="nope")
        with pytest.raises(ValueError, match="Invalid approval status"):
            create_approval_event("r", 7, tool_name="t", status="nope")

    def test_extra_event_helpers(self) -> None:
        ev = create_compacted_event("r", 1, original_events=[1, 2], compacted_data={"tokens": 5})
        assert ev["event_type"] == "model.output.compacted"
        assert create_tool_approved_event("r", 2, tool_name="t", tool_args={"a": 1})["event_type"] == "tool.approved"
        assert create_tool_rejected_event("r", 3, tool_name="t", reason="no")["event_type"] == "tool.rejected"
        assert create_workspace_changed_event("r", 4, changes=[])["event_type"] == "workspace.changed"
        assert create_verification_started_event("r", 5, target_run_id="t")["event_type"] == "verification.started"
        assert create_verification_completed_event("r", 6, verdict="pass", issues=[])["event_type"] == "verification.completed"

    @pytest.mark.asyncio
    async def test_store_event(self) -> None:
        db = AsyncMock()
        event = create_run_started("r", 1, employee_id="e", model_id="m")
        event_id = await store_event(db, event)
        assert event_id == event["event_id"]
        db.execute.assert_awaited_once()


class TestKnowledgeGeneration:
    @pytest.mark.asyncio
    async def test_get_active_generation_found_and_missing(self) -> None:
        row = {
            "id": "g1",
            "model_key": "m",
            "vector_dimension": 3,
            "source_event_sequence": 1,
            "status": "active",
            "created_at": "t",
            "activated_at": "t",
        }
        db = AsyncMock()
        db.execute = AsyncMock(return_value=AsyncMock(fetchone=AsyncMock(return_value=row)))
        assert await get_active_generation(db, "c1") == row
        db.execute = AsyncMock(return_value=AsyncMock(fetchone=AsyncMock(return_value=None)))
        assert await get_active_generation(db, "c1") is None

    @pytest.mark.asyncio
    async def test_list_and_count(self) -> None:
        db = AsyncMock()
        db.execute = AsyncMock(return_value=AsyncMock(fetchall=AsyncMock(return_value=[{"id": "g1"}])))
        assert await list_generations(db, "c1") == [{"id": "g1"}]
        db.execute = AsyncMock(return_value=AsyncMock(fetchone=AsyncMock(return_value={"cnt": 4})))
        assert await count_items_for_generation(db, "g1") == 4
        db.execute = AsyncMock(return_value=AsyncMock(fetchone=AsyncMock(return_value=None)))
        assert await count_items_for_generation(db, "g1") == 0

    @pytest.mark.asyncio
    async def test_count_lancedb_without_dependency(self) -> None:
        with patch.dict("sys.modules", {"lancedb": None}):
            assert await count_lancedb_items("c1") == 0
            assert await count_lancedb_items_for_generation("g1") == 0


class TestSkillVerify:
    def test_compute_package_hash(self, tmp_path) -> None:
        path = tmp_path / "pkg.bin"
        path.write_bytes(b"hello world")
        assert compute_package_hash(str(path)) == hashlib.sha256(b"hello world").hexdigest()

    def test_validate_package_paths(self, tmp_path) -> None:
        (tmp_path / "ok.txt").write_text("x")
        parent = tmp_path / "nested"
        parent.mkdir(exist_ok=True)
        (parent / "..escape").write_text("x")
        violations = validate_package_paths(str(tmp_path))
        assert any(".." in v for v in violations)
        clean = tmp_path / "clean"
        clean.mkdir(exist_ok=True)
        (clean / "safe.txt").write_text("x")
        assert validate_package_paths(str(clean)) == []

    def test_verify_skill_signature_valid_and_invalid(self, tmp_path) -> None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        pkg = tmp_path / "skill.zip"
        pkg.write_bytes(b"data")
        private_key = Ed25519PrivateKey.generate()
        public_key_hex = private_key.public_key().public_bytes_raw().hex()
        signature = private_key.sign(b"data").hex()
        assert verify_skill_signature(str(pkg), public_key_hex, signature) is True
        assert verify_skill_signature(str(pkg), public_key_hex, "00" * 64) is False
        assert verify_skill_signature(str(pkg), "zz", "00") is False

    def test_exception_type(self) -> None:
        assert issubclass(SkillVerificationError, ValueError)


class TestAssets:
    def test_get_asset_path(self) -> None:
        path = get_asset_path("manifest.json")
        assert Path(path).is_file()

    def test_list_assets(self) -> None:
        names = list_assets()
        assert "manifest.json" in names
        assert "manifest.schema.json" in names
