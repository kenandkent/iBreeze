"""Ed25519 signing key management for catalog releases."""
import hashlib
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
    key_dir.mkdir(parents=True, exist_ok=True)
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

    return private_pem, public_pem, kid


def get_current_keyset() -> dict:
    """Return the current signing keys JWK metadata."""
    key_dir = Path("keys")
    _, _, kid = load_or_create_signing_keys(key_dir)
    return {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "kid": kid,
                "use": "sig",
            }
        ]
    }
