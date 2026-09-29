"""Thin worker adapter around an injected compiled runtime."""

from collections.abc import Mapping
from typing import Protocol

from ..runtime_context import ProspectRuntimeContext


class CompiledProspectRuntime(Protocol):
    async def ainvoke(
        self,
        state: Mapping[str, object],
        *,
        context: ProspectRuntimeContext,
    ) -> Mapping[str, object]: ...


class ProspectAgentExecutor:
    def __init__(self, runtime: CompiledProspectRuntime) -> None:
        self._runtime = runtime

    async def execute(
        self,
        initial_state: Mapping[str, object],
        *,
        context: ProspectRuntimeContext,
    ) -> Mapping[str, object]:
        return await self._runtime.ainvoke(initial_state, context=context)
