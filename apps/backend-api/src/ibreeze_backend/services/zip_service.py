"""Strict Skill ZIP validation and hashing."""

from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from ibreeze_backend.skills.schemas import SkillManifest

MAX_OBJECT_BYTES = 50 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_ENTRIES = 1000


def validate_skill_zip(
    zip_path: Path,
    *,
    expected_key: str,
    expected_version: str,
) -> tuple[SkillManifest, str, str]:
    if zip_path.stat().st_size < 1 or zip_path.stat().st_size > MAX_OBJECT_BYTES:
        raise ValueError("SKILL_PACKAGE_SIZE_INVALID")
    object_sha256 = _file_sha256(zip_path)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ENTRIES:
                raise ValueError("SKILL_PACKAGE_ENTRY_LIMIT")
            normalized: dict[str, zipfile.ZipInfo] = {}
            total_size = 0
            for entry in entries:
                path = _normalize_path(entry.filename)
                if path in normalized:
                    raise ValueError("SKILL_PACKAGE_DUPLICATE_PATH")
                normalized[path] = entry
                total_size += entry.file_size
                if total_size > MAX_UNCOMPRESSED_BYTES:
                    raise ValueError("SKILL_PACKAGE_UNCOMPRESSED_LIMIT")
                mode = entry.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise ValueError("SKILL_PACKAGE_SPECIAL_FILE")
            manifest_entry = normalized.get("skill.json")
            if manifest_entry is None or manifest_entry.is_dir():
                raise ValueError("SKILL_MANIFEST_MISSING")
            if "instructions.md" not in normalized:
                raise ValueError("SKILL_INSTRUCTIONS_MISSING")
            try:
                raw_manifest = json.loads(archive.read(manifest_entry))
                manifest = SkillManifest.model_validate(raw_manifest)
            except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
                raise ValueError("SKILL_MANIFEST_INVALID") from exc
            _validate_manifest(
                archive,
                normalized,
                manifest,
                expected_key=expected_key,
                expected_version=expected_version,
            )
    except zipfile.BadZipFile as exc:
        raise ValueError("SKILL_PACKAGE_INVALID_ZIP") from exc
    canonical = json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return manifest, object_sha256, hashlib.sha256(canonical).hexdigest()


def _validate_manifest(
    archive: zipfile.ZipFile,
    entries: dict[str, zipfile.ZipInfo],
    manifest: SkillManifest,
    *,
    expected_key: str,
    expected_version: str,
) -> None:
    if manifest.key != expected_key or manifest.version != expected_version:
        raise ValueError("SKILL_MANIFEST_IDENTITY_MISMATCH")
    file_entries = {
        path
        for path, entry in entries.items()
        if not entry.is_dir() and path != "skill.json"
    }
    declared: dict[str, object] = {}
    for item in manifest.files:
        path = _normalize_path(item.path)
        if path == "skill.json" or path in declared:
            raise ValueError("SKILL_MANIFEST_FILE_SET_INVALID")
        if item.executable != (item.interpreter is not None):
            raise ValueError("SKILL_MANIFEST_EXECUTABLE_INVALID")
        declared[path] = item
        entry = entries.get(path)
        if entry is None or entry.is_dir():
            raise ValueError("SKILL_MANIFEST_FILE_SET_INVALID")
        actual = hashlib.sha256(archive.read(entry)).hexdigest()
        if actual != item.sha256:
            raise ValueError("SKILL_MANIFEST_FILE_HASH_MISMATCH")
    if set(declared) != file_entries or manifest.entrypoint not in declared:
        raise ValueError("SKILL_MANIFEST_FILE_SET_INVALID")
    _validate_domains(manifest.network_domains)


def _normalize_path(value: str) -> str:
    if "\\" in value or "\x00" in value:
        raise ValueError("SKILL_PACKAGE_PATH_INVALID")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("SKILL_PACKAGE_PATH_INVALID")
    return path.as_posix().rstrip("/")


def _validate_domains(values: list[str]) -> None:
    for value in values:
        if (
            not value
            or "://" in value
            or value == "*"
            or "/" in value
            or value.startswith(".")
            or value.endswith(".")
        ):
            raise ValueError("SKILL_NETWORK_DOMAIN_INVALID")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
