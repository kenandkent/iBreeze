from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "iBreeze Admin Backend"
    admin_db_path: str = "/tmp/ibreeze_admin.db"
    jwt_secret_key: str = "ibreeze-admin-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    host: str = "127.0.0.1"
    port: int = 50080

    model_config = {"env_prefix": "IBREEZE_ADMIN_"}


settings = Settings()
