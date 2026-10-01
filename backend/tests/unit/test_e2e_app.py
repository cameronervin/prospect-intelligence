"""Tests for the credential-free browser-test application factory."""

from typing import Any, cast

import pytest
from pydantic import SecretStr

from app.bootstrap.container import Container
from app.platform.config.settings import Environment, Settings
from tests.fakes import FakeDatabase


def test_scripted_runtime_uses_frontend_demo_identity() -> None:
    from tests.e2e_app import ScriptedModelRuntime

    runtime = ScriptedModelRuntime.for_frontend_demo()

    assert runtime.model.memory_path == "/memories/tenant-demo/alex-morgan/preferences.md"
    assert runtime.model.first_call_delay_seconds == 1.75
    assert runtime.models.orchestrator is runtime.model
    assert runtime.models.specialist is runtime.model


def test_e2e_factory_injects_scripted_runtime_into_production_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests import e2e_app

    settings = Settings(
        environment=Environment.TEST,
        external_live_enabled=False,
        online_quality_enabled=False,
    )
    container = Container(settings=settings, database=FakeDatabase())
    captured: dict[str, object] = {}

    def capture_container(
        actual_settings: Settings,
        *,
        model_runtime: object,
    ) -> Container:
        captured["settings"] = actual_settings
        captured["runtime"] = model_runtime
        return container

    monkeypatch.setattr(e2e_app, "build_container", capture_container)

    app = e2e_app.create_e2e_app(settings)

    assert app.state.container is container
    assert captured["settings"] is settings
    runtime = cast(Any, captured["runtime"])
    assert runtime.model.memory_path == "/memories/tenant-demo/alex-morgan/preferences.md"


@pytest.mark.parametrize(
    "settings",
    [
        Settings(
            environment=Environment.PRODUCTION,
            demo_auth_enabled=False,
            external_live_enabled=False,
            online_quality_enabled=False,
        ),
        Settings(environment=Environment.TEST, external_live_enabled=True),
        Settings(
            environment=Environment.TEST,
            online_quality_enabled=True,
            langsmith_api_key=SecretStr("test-only"),
            typesafe_api_key=SecretStr("test-only"),
        ),
    ],
)
def test_e2e_factory_rejects_live_or_production_configuration(settings: Settings) -> None:
    from tests.e2e_app import create_e2e_app

    with pytest.raises(RuntimeError, match="browser-test application requires"):
        create_e2e_app(settings)
