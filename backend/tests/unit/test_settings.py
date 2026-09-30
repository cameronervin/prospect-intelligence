"""Settings contract tests."""

import re
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
    assert settings.orchestrator_model == "gpt-5.6-sol"
    assert settings.subagent_model == "gpt-5.6-luna"
    assert settings.model_request_timeout_seconds == 60
    assert settings.model_retry_attempts == 2
    assert settings.openai_base_url is None
    assert settings.sec_app_name == "freight-prospect-takehome"
    assert settings.sec_contact_email == "contact@example.invalid"
    assert settings.sec_declared_user_agent == ("freight-prospect-takehome contact@example.invalid")


def test_openai_base_url_is_read_from_the_application_prefix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TAKEHOME_OPENAI_BASE_URL", "https://us.api.openai.com/v1/")

    assert Settings().openai_base_url == "https://us.api.openai.com/v1"

    monkeypatch.setenv("TAKEHOME_OPENAI_BASE_URL", "  ")

    assert Settings().openai_base_url is None


@pytest.mark.parametrize(
    "value",
    (
        "http://us.api.openai.com/v1",
        "https://user:secret@us.api.openai.com/v1",
        "https://us.api.openai.com/v1?api-key=secret",
        "https://us.api.openai.com/v1#fragment",
        "us.api.openai.com/v1",
    ),
)
def test_openai_base_url_rejects_unsafe_or_malformed_endpoints(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    value: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError) as error:
        Settings(openai_base_url=value)

    assert "secret" not in str(error.value)


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


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("sec_app_name", "freight prospect"),
        ("sec_app_name", '"freight-prospect"'),
        ("sec_app_name", "freight-prospect🚚"),
        ("sec_app_name", "freight-prospect\x7f"),
        ("sec_contact_email", "research @example.com"),
        ("sec_contact_email", '"research@example.com"'),
        ("sec_contact_email", "not-an-email"),
        ("sec_contact_email", "research🚚@example.com"),
        ("sec_contact_email", "research@example.com\x7f"),
    ),
)
def test_sec_identity_tokens_reject_whitespace_quotes_and_invalid_email(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    value: str,
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


_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_EXAMPLES = (
    _REPO_ROOT / "backend" / ".env.example",
    _REPO_ROOT / "deploy" / "envs" / ".env.local.example",
)


@pytest.mark.parametrize("path", _ENV_EXAMPLES, ids=lambda path: path.name)
def test_env_examples_are_portable_and_load_into_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    fields = {f"TAKEHOME_{name.upper()}" for name in Settings.model_fields}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        assert separator and re.fullmatch(r"[A-Z][A-Z0-9_]*", key), line
        # Keep examples portable across strict dotenv and Compose parsers.
        assert not re.search(r"\s", value), key
        assert '"' not in value and "'" not in value, key
        if key.startswith("TAKEHOME_"):
            assert key in fields, key

    settings = Settings(_env_file=path)  # pyright: ignore[reportCallIssue]

    assert settings.openai_base_url == "https://us.api.openai.com/v1"
    assert settings.sec_app_name == "freight-prospect-takehome"
    assert settings.sec_contact_email == "contact@example.invalid"
    assert settings.sec_declared_user_agent == ("freight-prospect-takehome contact@example.invalid")
