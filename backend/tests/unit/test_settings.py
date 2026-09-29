"""Settings contract tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.platform.config.settings import DEVELOPMENT_DATABASE_URL, Environment, Settings


def test_settings_have_safe_local_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings()

    assert settings.environment is Environment.DEVELOPMENT
    assert settings.database_url.get_secret_value() == DEVELOPMENT_DATABASE_URL
    assert settings.log_json is False
    assert settings.model_request_timeout_seconds == 60
    assert settings.model_retry_attempts == 2


def test_settings_reject_invalid_database_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError):
        Settings(database_connect_timeout_seconds=0)


@pytest.mark.parametrize(
    ("field", "value"),
    (("model_request_timeout_seconds", 0), ("model_retry_attempts", 6)),
)
def test_settings_reject_invalid_model_runtime_limits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    value: int,
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError):
        Settings(**{field: value})  # type: ignore[arg-type]


def test_provider_managed_langsmith_environment_does_not_extend_app_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_PROJECT", "freight-prospect-validation")

    settings = Settings()

    assert not hasattr(settings, "langsmith_tracing")
    assert not hasattr(settings, "langsmith_project")


def test_provider_keys_use_one_canonical_environment_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TAKEHOME_OPENAI_API_KEY", "legacy-alias")

    without_canonical_key = Settings()

    assert without_canonical_key.openai_api_key is None

    monkeypatch.setenv("OPENAI_API_KEY", "canonical-key")
    with_canonical_key = Settings()

    assert with_canonical_key.openai_api_key is not None
    assert with_canonical_key.openai_api_key.get_secret_value() == "canonical-key"
