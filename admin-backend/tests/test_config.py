from app.config import Settings


def test_default_settings():
    s = Settings()
    assert s.app_name == "iBreeze Admin Backend"
    assert s.port == 50080
    assert s.jwt_algorithm == "HS256"


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("IBREEZE_ADMIN_PORT", "9999")
    monkeypatch.setenv("IBREEZE_ADMIN_JWT_SECRET_KEY", "test-secret")
    s = Settings()
    assert s.port == 9999
    assert s.jwt_secret_key == "test-secret"
