"""Create four specialist chains and the root orchestrator Deep Agent."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,  # pyright: ignore[reportUnknownVariableType]
    register_harness_profile,
)
from deepagents._models import get_model_provider  # pyright: ignore[reportPrivateUsage]
from deepagents.backends import (
    BackendProtocol,
    CompositeBackend,
    FilesystemBackend,
    StateBackend,
    StoreBackend,
)
from deepagents.middleware.filesystem import FilesystemPermission
from deepagents.middleware.subagents import CompiledSubAgent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_quickjs import CodeInterpreterMiddleware
from langgraph.store.base import BaseStore

from ..contracts.agent_runtime import ProspectRuntimeContext
from .context import current_runtime_context
from .middleware import middleware_for_agent
from .specs import (
    AgentSpec,
    ModelClass,
    orchestrator_spec,
    specialist_specs,
)
from .state import ProspectDeepAgentState
from .tools import ToolRegistry

_profiled_providers: set[str] = set()


def _disable_implicit_subagent(model: BaseChatModel) -> None:
    provider = get_model_provider(model)
    if not provider:
        raise ValueError("Deep Agent models must expose a provider identifier")
    if provider in _profiled_providers:
        return
    register_harness_profile(
        provider,
        HarnessProfile(general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)),
    )
    _profiled_providers.add(provider)


def _memory_namespace(runtime: object) -> tuple[str, ...]:
    explicit = cast(ProspectRuntimeContext | None, cast(Any, runtime).context)
    context = current_runtime_context(explicit)
    return (*context.preference_namespace, "agent_files")


def create_agent_backend(spec: AgentSpec, store: BaseStore) -> StateBackend | CompositeBackend:
    routes: dict[str, BackendProtocol] = {}
    if "/memories/" in spec.readable_paths:
        routes["/memories/"] = StoreBackend(namespace=_memory_namespace, store=store)
    if spec.skill_sources:
        routes["/skills/"] = FilesystemBackend(Path(__file__).with_name("skills"))
    if not routes:
        return StateBackend()
    return CompositeBackend(
        default=StateBackend(),
        routes=routes,
    )


def _path_pattern(path: str) -> str:
    return f"{path}**" if path.endswith("/") else path


def filesystem_permissions(spec: AgentSpec) -> list[FilesystemPermission]:
    permissions = [
        FilesystemPermission(operations=["read"], paths=[_path_pattern(path)], mode="allow")
        for path in spec.readable_paths
    ]
    permissions.extend(
        FilesystemPermission(operations=["write"], paths=[path], mode="allow")
        for path in spec.writable_paths
    )
    permissions.extend(
        [
            FilesystemPermission(operations=["read"], paths=["/**"], mode="deny"),
            FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
        ]
    )
    return permissions


def create_agent_chain(
    *,
    spec: AgentSpec,
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    store: BaseStore,
    subagents: Sequence[CompiledSubAgent] = (),
) -> Runnable[dict[str, object], dict[str, object]]:
    """Build one model-facing chain; it never constructs another chain."""

    _disable_implicit_subagent(model)
    middleware: list[AgentMiddleware[Any, Any, Any]] = list(middleware_for_agent(spec))
    if spec.ptc_tool_names:
        middleware.append(
            CodeInterpreterMiddleware(
                ptc=list(spec.ptc_tool_names),
                mode="thread",
                timeout=5.0,
                memory_limit=64 * 1024 * 1024,
                max_ptc_calls=spec.max_tool_calls,
            )
        )
    return cast(
        Runnable[dict[str, object], dict[str, object]],
        create_deep_agent(
            model=model,
            tools=list(tools),
            system_prompt=f"{spec.description}\n\n{spec.system_prompt}",
            middleware=middleware,
            subagents=list(subagents),
            permissions=filesystem_permissions(spec),
            backend=create_agent_backend(spec, store),
            state_schema=ProspectDeepAgentState,
            context_schema=ProspectRuntimeContext,
            skills=list(spec.skill_sources) or None,
            name=spec.name,
        ),
    )


def _model_for_spec(
    spec: AgentSpec,
    *,
    orchestrator_model: BaseChatModel,
    specialist_model: BaseChatModel,
) -> BaseChatModel:
    if spec.model_class is ModelClass.ORCHESTRATOR:
        return orchestrator_model
    return specialist_model


def build_specialist_chains(
    *,
    orchestrator_model: BaseChatModel,
    specialist_model: BaseChatModel,
    tools: ToolRegistry,
    store: BaseStore,
) -> dict[str, Runnable[dict[str, object], dict[str, object]]]:
    return {
        spec.name: create_agent_chain(
            spec=spec,
            model=_model_for_spec(
                spec,
                orchestrator_model=orchestrator_model,
                specialist_model=specialist_model,
            ),
            tools=tools.resolve(spec.tool_names),
            store=store,
        )
        for spec in specialist_specs()
    }


def build_orchestrator_chain(
    *,
    orchestrator_model: BaseChatModel,
    specialist_model: BaseChatModel,
    tools: ToolRegistry,
    specialists: Mapping[str, Runnable[dict[str, object], dict[str, object]]],
    store: BaseStore,
) -> Runnable[dict[str, object], dict[str, object]]:
    spec = orchestrator_spec()
    if tuple(specialists) != spec.subagent_names:
        raise ValueError("orchestrator specialists must match the declared topology")
    subagents: list[CompiledSubAgent] = [
        {
            "name": specialist.name,
            "description": specialist.description,
            "runnable": specialists[specialist.name],
            "mode": "isolated",
        }
        for specialist in specialist_specs()
    ]
    return create_agent_chain(
        spec=spec,
        model=_model_for_spec(
            spec,
            orchestrator_model=orchestrator_model,
            specialist_model=specialist_model,
        ),
        tools=tools.resolve(spec.tool_names),
        store=store,
        subagents=subagents,
    )


@dataclass(frozen=True, slots=True)
class ProspectChains:
    specialists: Mapping[str, Runnable[dict[str, object], dict[str, object]]]
    orchestrator: Runnable[dict[str, object], dict[str, object]]


def build_chains(
    *,
    orchestrator_model: BaseChatModel,
    specialist_model: BaseChatModel,
    tools: ToolRegistry,
    store: BaseStore,
) -> ProspectChains:
    specialists = build_specialist_chains(
        orchestrator_model=orchestrator_model,
        specialist_model=specialist_model,
        tools=tools,
        store=store,
    )
    return ProspectChains(
        specialists=specialists,
        orchestrator=build_orchestrator_chain(
            orchestrator_model=orchestrator_model,
            specialist_model=specialist_model,
            tools=tools,
            specialists=specialists,
            store=store,
        ),
    )
