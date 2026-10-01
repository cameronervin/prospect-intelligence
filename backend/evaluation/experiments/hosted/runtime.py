"""OpenAI runtime composition for the hosted CAM-40 target."""

from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol

from app.platform.config.settings import Settings

from .plan import ExperimentVariant

type TargetFactory = Callable[[ExperimentVariant], object]


class AsyncTarget(Protocol):
    async def ainvoke(self, inputs: Mapping[str, object]) -> Mapping[str, object]: ...


async def _close(value: object) -> None:
    for method_name in ("aclose", "close"):
        close = getattr(value, method_name, None)
        if callable(close):
            result = close()
            if isinstance(result, Awaitable):
                await result
            return


class _OwnedTarget:
    def __init__(self, target: AsyncTarget, runtime: object) -> None:
        self._target = target
        self._runtime = runtime

    async def ainvoke(self, inputs: Mapping[str, object]) -> Mapping[str, object]:
        return await self._target.ainvoke(inputs)

    async def aclose(self) -> None:
        await _close(self._runtime)


def target_factory(settings: Settings) -> TargetFactory:
    def build(variant: ExperimentVariant) -> object:
        from app.platform.llm.openai import OpenAIModelRuntime
        from evaluation.targets.prospect_live import ProspectLiveTarget

        configured = settings.model_copy(
            update={
                "orchestrator_model": variant.orchestrator_model,
                "subagent_model": variant.specialist_model,
            }
        )
        runtime = OpenAIModelRuntime(configured)
        models = runtime.models
        target = ProspectLiveTarget(
            orchestrator_model=models.orchestrator,
            specialist_model=models.specialist,
            prompt_revision=variant.prompt_revision,
            interpreter_enabled=variant.interpreter_enabled,
        )
        return _OwnedTarget(target, runtime)

    return build
