"""Settings contract tests."""

import pytest
from pydantic import ValidationError

from app.platform.config.settings import DEVELOPMENT_DATABASE_URL, Environment, Settings


def test_settings_have_safe_local_defaults() -> None:
    settings = Settings()

    assert settings.environment is Environment.DEVELOPMENT
    assert settings.database_url.get_secret_value() == DEVELOPMENT_DATABASE_URL
    assert settings.log_json is False


def test_settings_reject_invalid_database_timeout() -> None:
    with pytest.raises(ValidationError):
        Settings(database_connect_timeout_seconds=0)
