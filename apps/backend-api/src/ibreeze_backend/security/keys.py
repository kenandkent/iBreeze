"""Persistent Ed25519 signing-key management."""

import base64
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def generate_ed25519_keypair() -> tuple[bytes, bytes]:
    """Generate an Ed25519 keypair. Returns (private_pem, public_pem)."""
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def load_or_create_signing_keys(
    key_dir: Path,
) -> tuple[bytes, bytes, str]:
    """Load existing signing keys or create new ones.

    Returns (private_pem, public_pem, kid).
    """
    key_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_path = key_dir / "signing_key.pem"
    public_path = key_dir / "signing_key.pub"
    kid_path = key_dir / "signing_key.kid"

    if private_path.exists() and public_path.exists() and kid_path.exists():
        private_pem = private_path.read_bytes()
        public_pem = public_path.read_bytes()
        kid = kid_path.read_text().strip()
        return private_pem, public_pem, kid

    private_pem, public_pem = generate_ed25519_keypair()
    kid = "ibreeze-key-" + hashlib.sha256(public_pem).hexdigest()[:12]

    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)
    kid_path.write_text(kid)
    os.chmod(private_path, 0o400)
    os.chmod(public_path, 0o444)
    os.chmod(kid_path, 0o444)

    return private_pem, public_pem, kid


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def public_jwk(public_pem: bytes, kid: str, *, status: str = "active") -> dict[str, str]:
    public_key = serialization.load_pem_public_key(public_pem)
    if not hasattr(public_key, "public_bytes"):
        raise ValueError("Invalid Ed25519 public key")
    public_raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return {
        "kty": "OKP",
        "crv": "Ed25519",
        "kid": kid,
        "use": "sig",
        "alg": "EdDSA",
        "x": b64url(public_raw),
        "status": status,
    }


def get_signed_keyset(key_dir: Path) -> dict[str, object]:
    """Return the append-only catalog keyset signed by the active catalog key."""
    private_pem, public_pem, kid = load_or_create_signing_keys(key_dir)
    issued_at = datetime.now(UTC)
    signed_payload: dict[str, object] = {
        "keys": [public_jwk(public_pem, kid)],
        "issued_at": issued_at.isoformat(),
        "expires_at": (issued_at + timedelta(hours=24)).isoformat(),
    }
    canonical = json.dumps(signed_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    private_key = serialization.load_pem_private_key(private_pem, password=None)
    signature = private_key.sign(canonical)
    return {
        **signed_payload,
        "signatures": [
            {
                "signing_key_id": kid,
                "signature_algorithm": "Ed25519",
                "signature": b64url(signature),
            }
        ],
    }
