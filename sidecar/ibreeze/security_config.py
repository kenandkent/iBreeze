"""Security configuration and utilities."""
import secrets
from pathlib import Path


def generate_api_key() -> str:
    """Generate a secure API key."""
    return secrets.token_urlsafe(32)


def validate_api_key(key: str) -> bool:
    """Validate API key format."""
    return len(key) >= 32


def get_secure_headers() -> dict[str, str]:
    """Get security headers for HTTP responses."""
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    }


class SecurityConfig:
    def __init__(self):
        self.api_key = generate_api_key()
        self.token_secret = generate_api_key()
        self.token_algorithm = "HS256"
        self.token_expire_minutes = 60

    def get_headers(self) -> dict[str, str]:
        return get_secure_headers()
