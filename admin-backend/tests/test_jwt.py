import pytest
from app.auth.jwt import create_access_token, create_refresh_token, decode_token


def test_create_and_decode_access_token():
    token = create_access_token("user-123", "super_admin")
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["role"] == "super_admin"
    assert payload["type"] == "access"


def test_create_and_decode_refresh_token():
    token = create_refresh_token("user-456")
    payload = decode_token(token)
    assert payload["sub"] == "user-456"
    assert payload["type"] == "refresh"
    assert "role" not in payload


def test_decode_invalid_token():
    with pytest.raises(Exception):
        decode_token("not-a-valid-token")


def test_decode_tampered_token():
    token = create_access_token("user-789", "viewer")
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(Exception):
        decode_token(tampered)
