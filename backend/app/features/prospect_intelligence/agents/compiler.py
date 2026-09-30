"""Bring specs, tools, middleware, chains, workflow, and persistence together."""

from typing import Any, cast

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from .chains import build_orchestrator_agent
from .graphs import build_prospect_workflow
from .runtime import CompiledProspectAgentRuntime, CompiledWorkflow
from .tools import build_tool_registry


def build_prospect_agent_runtime(
    *,
    orchestrator_model: BaseChatModel,
    specialist_model: BaseChatModel,
    checkpointer: BaseCheckpointSaver[Any],
    store: BaseStore,
) -> CompiledProspectAgentRuntime:
    """Compile the feature runtime once after persistence has started."""

    tools = build_tool_registry()
    orchestrator = build_orchestrator_agent(
        orchestrator_model=orchestrator_model,
        specialist_model=specialist_model,
        tools=tools,
        store=store,
    )
    graph = build_prospect_workflow(orchestrator)
    compiled = graph.compile(  # pyright: ignore[reportUnknownMemberType]
        checkpointer=checkpointer,
        store=store,
    )
    return CompiledProspectAgentRuntime(cast(CompiledWorkflow, compiled))
