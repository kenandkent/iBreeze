"""Security module tests — Ed25519 key generation, signing, verification.

Covers design spec sections:
- G.15 Cryptographic signing (Ed25519)
"""
import pytest


class TestSecurityKeys:
    """Ed25519 key generation and signing."""

    def test_generate_ed25519_keypair(self):
        from ibreeze_backend.security.keys import generate_ed25519_keypair

        private_pem, public_pem = generate_ed25519_keypair()
        assert private_pem is not None
        assert public_pem is not None
        assert len(private_pem) > 100
        assert len(public_pem) > 100
        assert b"PRIVATE KEY" in private_pem
        assert b"PUBLIC KEY" in public_pem

    def test_sign_and_verify(self):
        from ibreeze_backend.security.keys import generate_ed25519_keypair
        from cryptography.hazmat.primitives import serialization

        private_pem, public_pem = generate_ed25519_keypair()
        private_key = serialization.load_pem_private_key(private_pem, password=None)
        public_key = serialization.load_pem_public_key(public_pem)

        message = b"test message to sign"
        signature = private_key.sign(message)

        # Verify should not raise
        public_key.verify(signature, message)

    def test_invalid_signature(self):
        from ibreeze_backend.security.keys import generate_ed25519_keypair
        from cryptography.hazmat.primitives import serialization
        from cryptography.exceptions import InvalidSignature

        private_pem, public_pem = generate_ed25519_keypair()
        private_key = serialization.load_pem_private_key(private_pem, password=None)
        public_key = serialization.load_pem_public_key(public_pem)

        message = b"test message"
        signature = private_key.sign(message)

        # Verify with wrong message should fail
        with pytest.raises(InvalidSignature):
            public_key.verify(signature, b"wrong message")
