"""Tests for ibreeze.security.encryption module."""

from __future__ import annotations

import base64

from ibreeze.security.encryption import (
    decrypt,
    derive_key,
    encrypt,
    generate_api_key,
    hash_password,
    is_bcrypt_hash,
    sha256_hex,
    verify_password,
)


class TestDeriveKey:
    def test_derives_key_with_random_salt(self):
        key1, salt1 = derive_key("password123")
        key2, salt2 = derive_key("password123")
        # Different salts → different keys
        assert key1 != key2
        assert salt1 != salt2

    def test_derives_key_with_fixed_salt(self):
        salt = b"\x00" * 16
        key1, s1 = derive_key("password", salt=salt)
        key2, s2 = derive_key("password", salt=salt)
        assert key1 == key2
        assert s1 == salt
        assert s2 == salt

    def test_different_passwords_different_keys(self):
        salt = b"\x00" * 16
        key1, _ = derive_key("pass1", salt=salt)
        key2, _ = derive_key("pass2", salt=salt)
        assert key1 != key2


class TestEncryptDecrypt:
    def test_roundtrip(self):
        key, _ = derive_key("test-password")
        plaintext = "Hello, World!"
        ciphertext = encrypt(plaintext, key)
        assert ciphertext != plaintext
        decrypted = decrypt(ciphertext, key)
        assert decrypted == plaintext

    def test_different_plaintexts_different_ciphertexts(self):
        key, _ = derive_key("key")
        ct1 = encrypt("message1", key)
        ct2 = encrypt("message2", key)
        assert ct1 != ct2

    def test_unicode_roundtrip(self):
        key, _ = derive_key("unicode-key")
        text = "你好世界 🌍"
        ct = encrypt(text, key)
        assert decrypt(ct, key) == text


class TestHashPassword:
    def test_hash_returns_string(self):
        h = hash_password("mypassword")
        assert isinstance(h, str)
        assert len(h) > 0

    def test_same_password_different_hashes(self):
        h1 = hash_password("samepass")
        h2 = hash_password("samepass")
        assert h1 != h2

    def test_verify_correct_password(self):
        password = "correct-password"
        h = hash_password(password)
        assert verify_password(password, h) is True

    def test_verify_wrong_password(self):
        h = hash_password("password")
        assert verify_password("wrong-password", h) is False


class TestGenerateApiKey:
    def test_generates_string(self):
        key = generate_api_key()
        assert isinstance(key, str)

    def test_key_is_base64_urlsafe(self):
        key = generate_api_key()
        # Should not raise
        decoded = base64.urlsafe_b64decode(key + "==")
        assert len(decoded) == 32

    def test_different_keys_each_time(self):
        k1 = generate_api_key()
        k2 = generate_api_key()
        assert k1 != k2


class TestSha256Hex:
    def test_returns_hex_string(self):
        result = sha256_hex(b"hello")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_deterministic(self):
        r1 = sha256_hex(b"test")
        r2 = sha256_hex(b"test")
        assert r1 == r2

    def test_empty_bytes(self):
        result = sha256_hex(b"")
        assert isinstance(result, str)
        assert len(result) == 64


class TestIsBcryptHash:
    def test_bcrypt_prefix(self):
        assert is_bcrypt_hash("$2b$10$abcdefghijklmnop") is True
        assert is_bcrypt_hash("$2a$10$abcdefghijklmnop") is True
        assert is_bcrypt_hash("$2y$10$abcdefghijklmnop") is True

    def test_non_bcrypt(self):
        assert is_bcrypt_hash("argon2id$...") is False
        assert is_bcrypt_hash("$5$hash") is False
        assert is_bcrypt_hash("plaintext") is False
