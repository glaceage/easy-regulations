from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/easy_regulations"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "easy-regulations"
    minio_region: str = "us-east-1"

    xiaomi_base_url: str = "https://api.xiaomi.com/v1"
    xiaomi_api_key: str = ""
    xiaomi_model: str = "MiMo-V2.5-Pro"

    auth_mode: str = "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
