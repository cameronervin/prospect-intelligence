"""Dependency composition without provider construction at import time."""

from typing import Protocol

from ..definitions import AgentSuite
from ..graphs import ProspectGraphBlueprint, create_prospect_graph_blueprint
from ..runtime_context import ProspectRuntimeContext


class AgentRuntimeCompiler(Protocol):
    def compile(
        self,
        *,
        suite: AgentSuite,
        topology: ProspectGraphBlueprint,
        context: ProspectRuntimeContext,
    ) -> object: ...


def compile_prospect_runtime(
    *,
    compiler: AgentRuntimeCompiler,
    suite: AgentSuite,
    context: ProspectRuntimeContext,
) -> object:
    return compiler.compile(
        suite=suite,
        topology=create_prospect_graph_blueprint(),
        context=context,
    )
