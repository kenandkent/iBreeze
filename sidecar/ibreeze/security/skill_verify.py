"""Skill package signature verification and path validation."""

from __future__ import annotations

import hashlib
from pathlib import Path


class SkillVerificationError(ValueError):
    pass


def verify_skill_signature(
    package_path: str,
    public_key_hex: str,
    signature_hex: str,
) -> bool:
    """Verify Ed25519 signature of a skill package."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        public_key_bytes = bytes.fromhex(public_key_hex)
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        signature = bytes.fromhex(signature_hex)
        with open(package_path, "rb") as f:
            data = f.read()
        public_key.verify(signature, data)
        return True
    except Exception:
        return False


def validate_package_paths(package_dir: str) -> list[str]:
    """Validate no path traversal in skill package filenames."""
    violations: list[str] = []
    for root, dirs, files in Path(package_dir).walk():
        for name in files + dirs:
            if ".." in name or name.startswith("/"):
                violations.append(str(Path(root) / name))
    return violations


def compute_package_hash(package_path: str) -> str:
    """Compute SHA-256 hash of a skill package."""
    h = hashlib.sha256()
    with open(package_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
