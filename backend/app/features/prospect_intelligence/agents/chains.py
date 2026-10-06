"""Create declarative specialists and the root orchestrator Deep Agent."""

from pathlib import Path
from typing import Any, cast

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,  # pyright: ignore[reportUnknownVariableType]
    register_harness_profile,
)
from deepagents._models import get_model_provider  # pyright: ignore[reportPrivateUsage]
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend, StoreBackend
from deepagents.middleware.filesystem import FilesystemPermission
from deepagents.middleware.subagents import SubAgent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_quickjs import CodeInterpreterMiddleware
from langgraph.store.base import BaseStore

from ..contracts.agent_runtime import ProspectRuntimeContext
from .context import current_runtime_context
from .middleware import middleware_for_agent
from .prompts import render_system_prompt
from .specs import AgentSpec, ModelClass, PromptRevision, orchestrator_spec, specialist_specs
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
    explicit = cast(ProspectRuntimeContext | None, getattr(runtime, "context", None))
    context = current_runtime_context(explicit)
    return (*context.preference_namespace, "agent_files")


def create_shared_backend(store: BaseStore) -> CompositeBackend:
    """Create the one virtual filesystem shared by the orchestrator and specialists."""

    return CompositeBackend(
        default=StateBackend(),
        routes={
            "/memories/": StoreBackend(namespace=_memory_namespace, store=store),
            "/skills/": FilesystemBackend(
                Path(__file__).with_name("skills"),
                virtual_mode=True,
            ),
        },
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


def _middleware_for_spec(
    spec: AgentSpec,
    *,
    interpreter_enabled: bool = True,
) -> list[AgentMiddleware[Any, Any, Any]]:
    middleware: list[AgentMiddleware[Any, Any, Any]] = list(middleware_for_agent(spec))
    if interpreter_enabled and spec.ptc_tool_names:
        middleware.append(
            CodeInterpreterMiddleware(
                ptc=list(spec.ptc_tool_names),
                mode="thread",
                timeout=5.0,
                memory_limit=64 * 1024 * 1024,
                max_ptc_calls=spec.max_tool_calls,
            )
        )
    return middleware


def _model_for_spec(
    spec: AgentSpec,
    *,
    orchestrator_model: BaseChatModel,
    specialist_model: BaseChatModel,
) -> BaseChatModel:
    if spec.model_class is ModelClass.ORCHESTRATOR:
        return orchestrator_model
    return specialist_model


def build_specialist_subagents(
    *,
    orchestrator_model: BaseChatModel,
    specialist_model: BaseChatModel,
    tools: ToolRegistry,
    interpreter_enabled: bool = True,
) -> tuple[SubAgent, ...]:
    """Build raw specs that Deep Agents compiles with ``create_agent``."""

    subagents: list[SubAgent] = []
    for spec in specialist_specs():
        subagent: SubAgent = {
            "name": spec.name,
            "description": spec.description,
            "system_prompt": render_system_prompt(spec),
            "mode": "isolated",
            "model": _model_for_spec(
                spec,
                orchestrator_model=orchestrator_model,
                specialist_model=specialist_model,
            ),
            # Explicit, including empty lists, so root-only tools are never inherited.
            "tools": list(tools.resolve(spec.tool_names)),
            "middleware": _middleware_for_spec(
                spec,
                interpreter_enabled=interpreter_enabled,
            ),
            # Explicit so the broader orchestrator policy is never inherited.
            "permissions": filesystem_permissions(spec),
        }
        if spec.skill_sources:
            subagent["skills"] = list(spec.skill_sources)
        subagents.append(subagent)
    return tuple(subagents)


def build_orchestrator_agent(
    *,
    orchestrator_model: BaseChatModel,
    specialist_model: BaseChatModel,
    tools: ToolRegistry,
    store: BaseStore,
    prompt_revision: PromptRevision = "outreach-v4",
    interpreter_enabled: bool = True,
) -> Runnable[dict[str, object], dict[str, object]]:
    """Build the single Deep Agent harness for the prospect workflow."""

    spec = orchestrator_spec(prompt_revision)
    _disable_implicit_subagent(orchestrator_model)
    subagents = build_specialist_subagents(
        orchestrator_model=orchestrator_model,
        specialist_model=specialist_model,
        tools=tools,
        interpreter_enabled=interpreter_enabled,
    )
    if tuple(subagent["name"] for subagent in subagents) != spec.subagent_names:
        raise ValueError("orchestrator specialists must match the declared topology")
    return cast(
        Runnable[dict[str, object], dict[str, object]],
        create_deep_agent(
            model=orchestrator_model,
            tools=list(tools.resolve(spec.tool_names)),
            system_prompt=render_system_prompt(spec),
            middleware=_middleware_for_spec(spec),
            subagents=list(subagents),
            permissions=filesystem_permissions(spec),
            backend=create_shared_backend(store),
            state_schema=ProspectDeepAgentState,
            context_schema=ProspectRuntimeContext,
            name=spec.name,
        ),
    )
