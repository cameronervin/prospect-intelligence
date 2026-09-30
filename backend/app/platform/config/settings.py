"""Validated application settings."""

from enum import StrEnum
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_DATABASE_URL = "postgresql+psycopg://takehome:takehome@localhost:5432/takehome"


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings plus canonical provider credential variables.

    Application-owned fields use ``TAKEHOME_``. Provider keys retain their single
    standard names so SDK configuration is not duplicated through aliases.
    """

    model_config = SettingsConfigDict(
        env_prefix="TAKEHOME_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        frozen=True,
        validate_default=True,
        hide_input_in_errors=True,
    )

    service_name: str = Field(default="langchain-takehome-backend", min_length=1, max_length=64)
    environment: Environment = Environment.DEVELOPMENT
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_json: bool = False
    docs_enabled: bool = True
    database_url: SecretStr = SecretStr(DEVELOPMENT_DATABASE_URL)
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)
    database_statement_timeout_ms: int = Field(default=5_000, ge=100, le=60_000)
    model_provider: str = Field(default="openai", min_length=1, max_length=32)
    orchestrator_model: str = Field(default="gpt-5.6-sol", min_length=1, max_length=128)
    subagent_model: str = Field(default="gpt-5.6-luna", min_length=1, max_length=128)
    orchestrator_reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    model_request_timeout_seconds: int = Field(default=60, ge=1, le=300)
    model_retry_attempts: int = Field(default=2, ge=0, le=5)
    openai_base_url: str | None = Field(default=None, max_length=512)
    external_live_enabled: bool = False
    external_request_timeout_seconds: int = Field(default=10, ge=1, le=60)
    external_retry_attempts: int = Field(default=2, ge=0, le=5)
    sec_user_agent: str = Field(
        default="freight-prospect-takehome contact@example.invalid",
        min_length=8,
        max_length=256,
    )
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
    )
    langsmith_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="LANGSMITH_API_KEY",
    )
    typesafe_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="TYPESAFE_API_KEY",
    )
    tavily_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="TAVILY_API_KEY",
    )
    fmcsa_web_key: SecretStr | None = Field(
        default=None,
        validation_alias="FMCSA_WEB_KEY",
    )

    @field_validator("openai_base_url")
    @classmethod
    def _validate_openai_base_url(cls, value: str | None) -> str | None:
        """Accept only a credential-free HTTPS endpoint; errors never echo the value."""

        if value is None or not value.strip():
            return None
        parts = urlsplit(value.strip())
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
        ):
            raise ValueError("openai_base_url must be a credential-free https URL")
        return parts.geturl().rstrip("/")
