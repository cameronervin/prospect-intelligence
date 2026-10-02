"""Credential-free ASGI entrypoint for the full-stack browser test."""

from dataclasses import dataclass

from fastapi import FastAPI

from app.bootstrap.wiring import build_container
from app.main import create_app
from app.platform.config.settings import Environment, Settings
from app.platform.llm import ModelSet
from tests.unit.prospect_intelligence.agent_test_support import TrajectoryModel

_FRONTEND_DEMO_MEMORY = "/memories/tenant-demo/alex-morgan/preferences.md"


@dataclass(slots=True)
class ScriptedModelRuntime:
    """Managed runtime that uses the deterministic graph trajectory without providers."""

    model: TrajectoryModel

    @classmethod
    def for_frontend_demo(cls) -> "ScriptedModelRuntime":
        return cls(
            TrajectoryModel(
                memory_path=_FRONTEND_DEMO_MEMORY,
                first_call_delay_seconds=1.75,
                account_name="Sysco Corporation",
            )
        )

    @property
    def models(self) -> ModelSet:
        return ModelSet(orchestrator=self.model, specialist=self.model)

    async def close(self) -> None:
        return None


def create_e2e_app(settings: Settings | None = None) -> FastAPI:
    """Build the production container with only the model provider replaced."""

    resolved_settings = settings or Settings()
    if (
        resolved_settings.environment is not Environment.TEST
        or resolved_settings.external_live_enabled
        or resolved_settings.online_quality_enabled
    ):
        raise RuntimeError(
            "browser-test application requires the test environment with external and online "
            "quality integrations disabled"
        )
    container = build_container(
        resolved_settings,
        model_runtime=ScriptedModelRuntime.for_frontend_demo(),
    )
    return create_app(resolved_settings, container=container)
