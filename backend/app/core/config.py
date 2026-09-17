from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    environment: str = "development"
    api_key: str = "changeme-dev-key"

    # Postgres
    database_url: str = (
        "postgresql+asyncpg://pulse:pulse@postgres:5432/pulse"
    )

    # Redis
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # Rate limits (per-minute, enforced via Redis token bucket in Phase 4)
    rate_limit_email_per_minute: int = 100
    rate_limit_sms_per_minute: int = 30
    rate_limit_push_per_minute: int = 200

    # Logging
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
