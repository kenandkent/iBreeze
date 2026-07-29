"""Tests for content-addressable artifact storage."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from ibreeze.artifacts.storage import ArtifactStorage, get_storage


class TestArtifactStorage:
    def test_write_and_read(self, tmp_path: Path) -> None:
        storage = ArtifactStorage(base_path=str(tmp_path))
        content = b"hello world"
        result = storage.write(content)
        assert result["existed"] is False
        assert result["sha256"] == hashlib.sha256(content).hexdigest()
        read_back = storage.read(result["sha256"])
        assert read_back == content

    def test_dedup(self, tmp_path: Path) -> None:
        storage = ArtifactStorage(base_path=str(tmp_path))
        content = b"hello world"
        r1 = storage.write(content)
        assert r1["existed"] is False
        r2 = storage.write(content)
        assert r2["existed"] is True
        assert r1["sha256"] == r2["sha256"]

    def test_company_id_changes_hash(self, tmp_path: Path) -> None:
        storage = ArtifactStorage(base_path=str(tmp_path))
        content = b"hello world"
        r_plain = storage.write(content, company_id="")
        r_c1 = storage.write(content, company_id="c1")
        assert r_plain["sha256"] != r_c1["sha256"]

    def test_exists(self, tmp_path: Path) -> None:
        storage = ArtifactStorage(base_path=str(tmp_path))
        content = b"hello world"
        sha = storage.compute_hash(content)
        assert storage.exists(sha) is False
        storage.write(content)
        assert storage.exists(sha) is True

    def test_read_missing(self, tmp_path: Path) -> None:
        storage = ArtifactStorage(base_path=str(tmp_path))
        assert storage.read("nonexistent") is None

    def test_compute_hash(self, tmp_path: Path) -> None:
        storage = ArtifactStorage(base_path=str(tmp_path))
        content = b"hello world"
        expected = hashlib.sha256(content).hexdigest()
        assert storage.compute_hash(content) == expected

    def test_get_storage_singleton(self) -> None:
        s1 = get_storage()
        s2 = get_storage()
        assert s1 is s2

    def test_write_failure_cleanup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        storage = ArtifactStorage(base_path=str(tmp_path))

        def failing_rename(src: str, dst: str) -> None:
            raise OSError("simulated failure")

        monkeypatch.setattr(os, "rename", failing_rename)

        with pytest.raises(OSError):
            storage.write(b"test data")

        objects_dir = tmp_path / "objects" / "sha256"
        if objects_dir.exists():
            for prefix_dir in objects_dir.iterdir():
                remaining = list(prefix_dir.iterdir())
                assert len(remaining) == 0
