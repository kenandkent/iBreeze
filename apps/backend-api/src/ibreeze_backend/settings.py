"""Application settings."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://ibreeze:ibreeze@localhost:5432/ibreeze"
    db_echo: bool = False
    api_key: str = "dev-api-key-change-me"
    token_secret: str = "dev-token-secret-change-me"
    token_algorithm: str = "EdDSA"
    token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    default_admin_username: str = "admin"
    default_admin_password: str = "admin123456"
    log_level: str = "INFO"
    log_json: bool = True

    model_config = {"env_prefix": "IBREEZE_"}


settings = Settings()
