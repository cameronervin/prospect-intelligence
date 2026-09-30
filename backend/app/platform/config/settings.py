"""Validated application settings."""

from enum import StrEnum
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
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
    online_quality_enabled: bool = False
    online_quality_sample_rate: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
    )
    online_quality_batch_size: int = Field(default=10, ge=1, le=100)
    online_quality_poll_seconds: float = Field(default=1.0, gt=0, le=60)
    online_quality_publish_timeout_seconds: float = Field(default=75.0, ge=10, le=300)
    langsmith_alert_webhook_url: SecretStr | None = None
    sec_app_name: str = Field(
        default="freight-prospect-takehome",
        min_length=1,
        max_length=128,
        pattern=r"^[^\s\"']+$",
    )
    sec_contact_email: str = Field(
        default="contact@example.invalid",
        min_length=3,
        max_length=254,
        pattern=r"^[^@\s\"']+@[^@\s\"']+\.[^@\s\"']+$",
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

    @model_validator(mode="after")
    def _validate_online_quality_credentials(self) -> "Settings":
        if not self.online_quality_enabled:
            return self
        configured = (
            self.langsmith_api_key is not None
            and bool(self.langsmith_api_key.get_secret_value().strip())
            and self.typesafe_api_key is not None
            and bool(self.typesafe_api_key.get_secret_value().strip())
        )
        if not configured:
            raise ValueError("online quality requires LangSmith and TypeSafe credentials")
        return self

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

    @field_validator("langsmith_alert_webhook_url")
    @classmethod
    def _validate_langsmith_alert_webhook_url(cls, value: SecretStr | None) -> SecretStr | None:
        """Accept only a secret, credential-free HTTPS webhook endpoint."""

        if value is None or not value.get_secret_value().strip():
            return None
        parts = urlsplit(value.get_secret_value().strip())
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
        ):
            raise ValueError("langsmith alert webhook must be a credential-free https URL")
        return SecretStr(parts.geturl())

    @field_validator("sec_app_name", "sec_contact_email")
    @classmethod
    def _validate_sec_header_token(cls, value: str) -> str:
        """Reject values that cannot be serialized safely as an HTTP header."""

        if not value.isascii() or any(
            ord(character) < 33 or ord(character) > 126 for character in value
        ):
            raise ValueError("SEC identity tokens must contain visible ASCII characters only")
        return value

    @property
    def sec_declared_user_agent(self) -> str:
        """Compose the SEC-declared identity from individually portable environment tokens."""

        return f"{self.sec_app_name} {self.sec_contact_email}"
