from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env also holds POSTGRES_* keys used only by Docker
    )

    project_name: str = "Ride Booking System"
    environment: Literal["local", "test", "production"] = "local"
    log_level: str = "INFO"

    database_url: str
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = Field(min_length=32)  # signing key for JWTs
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    @model_validator(mode="after")
    def _reject_placeholder_secret_in_production(self) -> "Settings":
        if self.environment == "production" and self.secret_key.startswith("replace_me"):
            raise ValueError("SECRET_KEY must be a real random value in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()