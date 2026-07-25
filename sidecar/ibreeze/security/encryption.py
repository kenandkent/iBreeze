"""Fernet symmetric encryption for data at rest, password hashing, API key generation."""

from __future__ import annotations

import base64
import hashlib
import os

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def derive_key(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """Derive Fernet key from password using PBKDF2. Returns (key, salt)."""
    if salt is None:
        salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key, salt


def encrypt(plaintext: str, key: bytes) -> str:
    """Encrypt string, return base64-encoded ciphertext."""
    f = Fernet(key)
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str, key: bytes) -> str:
    """Decrypt base64-encoded ciphertext."""
    f = Fernet(key)
    return f.decrypt(ciphertext.encode()).decode()


_ph = PasswordHasher(
    time_cost=4,
    memory_cost=65536,  # 64 MiB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Hash password using Argon2id (OWASP 2024 recommended params)."""
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against Argon2id hash."""
    try:
        return _ph.verify(hashed, password)
    except VerifyMismatchError:
        return False


def generate_api_key() -> str:
    """Generate a random API key."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def sha256_hex(data: bytes) -> str:
    """SHA-256 hash as hex string."""
    return hashlib.sha256(data).hexdigest()


def is_bcrypt_hash(hashed: str) -> bool:
    """Check if a hash is bcrypt format (for migration)."""
    return hashed.startswith("$2")


def migrate_password(password: str, old_hash: str) -> str | None:
    """Verify against old bcrypt hash and return new Argon2id hash if valid.
    Returns None if old hash verification fails.
    """
    if not is_bcrypt_hash(old_hash):
        return None
    import bcrypt

    try:
        if bcrypt.checkpw(password.encode(), old_hash.encode()):
            return hash_password(password)
    except Exception:
        pass
    return None
