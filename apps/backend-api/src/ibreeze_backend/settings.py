"""Application settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    public_origin: str = "http://127.0.0.1:51080"
    database_url: str = "postgresql+asyncpg://ibreeze:ibreeze@localhost:51543/ibreeze"
    db_echo: bool = False
    api_key: str = "dev-api-key-change-me"
    token_secret: str = "dev-token-secret-change-me"
    token_algorithm: str = "EdDSA"
    token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    auth_key_dir: str = "runtime-keys/auth"
    catalog_key_dir: str = "runtime-keys/catalog"
    default_admin_username: str = "admin"
    default_admin_password: str = "admin123456"
    log_level: str = "INFO"
    log_json: bool = True

    # S3 配置
    s3_endpoint_url: str = "http://localhost:51900"
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: str = "minioadmin"
    s3_bucket_name: str = "ibreeze"
    s3_region: str = "us-east-1"

    model_config = {"env_prefix": "IBREEZE_"}


settings = Settings()
