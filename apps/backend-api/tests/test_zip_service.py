"""ZIP validation service tests."""

import base64
import io
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ibreeze_backend.services.zip_service import (
    compute_zip_checksum,
    validate_uncompressed_size,
    validate_zip_size,
    validate_zip_structure,
    verify_signature,
)


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _write_zip(tmp_path: Path, name: str, data: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(data)
    return p


# ---------------------------------------------------------------------------
# validate_zip_structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_zip_structure_valid(tmp_path: Path):
    """Test that a valid skill ZIP passes validation."""
    data = _make_zip({"manifest.json": "{}", "main.py": "print('ok')"})
    path = _write_zip(tmp_path, "valid.zip", data)

    ok, errors = validate_zip_structure(path)
    assert ok is True
    assert errors == []


@pytest.mark.asyncio
async def test_validate_zip_structure_missing_manifest(tmp_path: Path):
    """Test that a ZIP without manifest.json fails."""
    data = _make_zip({"main.py": "print('ok')"})
    path = _write_zip(tmp_path, "no_manifest.zip", data)

    ok, errors = validate_zip_structure(path)
    assert ok is False
    assert "Missing manifest.json" in errors


@pytest.mark.asyncio
async def test_validate_zip_structure_missing_py(tmp_path: Path):
    """Test that a ZIP without .py files fails."""
    data = _make_zip({"manifest.json": "{}"})
    path = _write_zip(tmp_path, "no_py.zip", data)

    ok, errors = validate_zip_structure(path)
    assert ok is False
    assert "No Python skill files found" in errors


@pytest.mark.asyncio
async def test_validate_zip_structure_path_traversal(tmp_path: Path):
    """Test that a ZIP with path traversal entries is rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", "{}")
        zf.writestr("main.py", "print('ok')")
        zf.writestr("../evil.py", "evil")
    path = _write_zip(tmp_path, "traversal.zip", buf.getvalue())

    ok, errors = validate_zip_structure(path)
    assert ok is False
    assert any("Suspicious path" in e for e in errors)


@pytest.mark.asyncio
async def test_validate_zip_bad_zip(tmp_path: Path):
    """Test that a non-ZIP file fails validation."""
    path = _write_zip(tmp_path, "bad.zip", b"not a zip file")

    ok, errors = validate_zip_structure(path)
    assert ok is False
    assert "Invalid ZIP file" in errors


# ---------------------------------------------------------------------------
# compute_zip_checksum
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_zip_checksum(tmp_path: Path):
    """Test computing SHA256 checksum of a ZIP file."""
    data = _make_zip({"manifest.json": "{}", "main.py": "x"})
    path = _write_zip(tmp_path, "checksum.zip", data)

    checksum = compute_zip_checksum(path)
    assert isinstance(checksum, str)
    assert len(checksum) == 64  # SHA256 hex length

    checksum2 = compute_zip_checksum(path)
    assert checksum == checksum2  # deterministic


# ---------------------------------------------------------------------------
# validate_zip_size
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_zip_size(tmp_path: Path):
    """Test ZIP upload size validation."""
    data = _make_zip({"manifest.json": "{}", "main.py": "print('ok')"})
    path = _write_zip(tmp_path, "size.zip", data)

    assert validate_zip_size(path) is True

    huge_size = 60 * 1024 * 1024
    huge_data = b"x" * huge_size
    huge_path = _write_zip(tmp_path, "huge.zip", huge_data)

    assert validate_zip_size(huge_path) is False


# ---------------------------------------------------------------------------
# validate_uncompressed_size
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_uncompressed_size(tmp_path: Path):
    """Test uncompressed size validation."""
    data = _make_zip({"manifest.json": "{}", "main.py": "print('ok')"})
    path = _write_zip(tmp_path, "uncomp.zip", data)

    assert validate_uncompressed_size(path) is True


# ---------------------------------------------------------------------------
# verify_signature
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_signature_valid(tmp_path: Path):
    """Test verifying a valid Ed25519 signature."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    data = b"hello world"
    path = _write_zip(tmp_path, "signed.zip", data)

    signature = private_key.sign(data)
    sig_b64 = base64.b64encode(signature).decode()

    assert verify_signature(path, sig_b64, public_pem) is True


@pytest.mark.asyncio
async def test_verify_signature_invalid(tmp_path: Path):
    """Test that an invalid signature is rejected."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    data = b"hello world"
    path = _write_zip(tmp_path, "bad_sig.zip", data)

    fake_sig = base64.b64encode(b"\x00" * 64).decode()

    assert verify_signature(path, fake_sig, public_pem) is False


@pytest.mark.asyncio
async def test_verify_signature_wrong_key(tmp_path: Path):
    """Test that a signature from a different key is rejected."""
    key1 = Ed25519PrivateKey.generate()
    key2 = Ed25519PrivateKey.generate()
    pub2_pem = (
        key2.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )

    data = b"hello world"
    path = _write_zip(tmp_path, "wrong_key.zip", data)

    sig = key1.sign(data)
    sig_b64 = base64.b64encode(sig).decode()

    assert verify_signature(path, sig_b64, pub2_pem) is False
