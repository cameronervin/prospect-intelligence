"""Validated application settings."""

from enum import StrEnum
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_DATABASE_URL = "postgresql+psycopg://takehome:takehome@localhost:5432/takehome"


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Settings loaded from ``TAKEHOME_`` environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="TAKEHOME_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=False,
        frozen=True,
        validate_default=True,
    )

    service_name: str = Field(default="langchain-takehome-backend", min_length=1, max_length=64)
    environment: Environment = Environment.DEVELOPMENT
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_json: bool = False
    docs_enabled: bool = True
    database_url: SecretStr = SecretStr(DEVELOPMENT_DATABASE_URL)
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)
    database_statement_timeout_ms: int = Field(default=5_000, ge=100, le=60_000)
