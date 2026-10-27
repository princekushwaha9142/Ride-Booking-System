from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables (and .env locally).

    Real environment variables take priority over the .env file.
    A required field with no default (database_url) makes startup fail
    immediately with a clear error instead of failing later at runtime.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env also holds POSTGRES_* keys used only by Docker
    )

    project_name: str = "Ride Booking System"
    environment: Literal["local", "test", "production"] = "local"
    log_level: str = "INFO"

    database_url: str  # required, no default
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    redis_url: str = "redis://localhost:6379/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()