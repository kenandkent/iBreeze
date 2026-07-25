"""Artifact CAS, manifest, and diff services."""

from ibreeze.artifacts.diff import (
    generate_text_diff,
    is_text_content,
    should_generate_diff,
)
from ibreeze.artifacts.manifest import Manifest, ManifestEntry
from ibreeze.artifacts.service import (
    create_artifact,
    create_artifact_with_manifest,
    get_artifact,
    get_artifact_content,
    get_artifact_version_chain,
    list_artifacts,
)
from ibreeze.artifacts.storage import ArtifactStorage, get_storage

__all__ = [
    "ArtifactStorage",
    "Manifest",
    "ManifestEntry",
    "create_artifact",
    "create_artifact_with_manifest",
    "generate_text_diff",
    "get_artifact",
    "get_artifact_content",
    "get_artifact_version_chain",
    "get_storage",
    "is_text_content",
    "list_artifacts",
    "should_generate_diff",
]
