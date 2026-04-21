from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Channel Intelligence API"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://cip:cip@localhost:5432/cip"
    database_url_sync: str = "postgresql://cip:cip@localhost:5432/cip"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    # Local development only. "broker" = normal Celery + Redis. "in_process_thread" = PM commit runs in a
    # daemon thread inside the API process (no broker/worker). Never use in production.
    cip_dev_celery_dispatch: Literal["broker", "in_process_thread"] = Field(
        default="broker",
        description="Dev-only Celery dispatch mode (env CIP_DEV_CELERY_DISPATCH).",
    )
    # `localhost` vs `127.0.0.1` are different browser origins — include both for local Next dev.
    api_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    storage_backend: str = "local"
    local_storage_path: str = "./storage/uploads"
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None

    # Promo plan exports (CPOR-style). Email is optional; manual download is the default path.
    promo_export_email_enabled: bool = False
    promo_export_default_recipient: str | None = None

    # When true, exposes POST /api/v1/dev/database-wipe (Settings UI). Never enable in shared/prod.
    allow_db_wipe: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
