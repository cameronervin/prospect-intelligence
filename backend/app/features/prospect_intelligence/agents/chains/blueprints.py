"""Describe individual agent runtimes without constructing provider clients."""

from dataclasses import dataclass
from typing import Protocol

from ..context.policies import PhaseContextPolicy, get_policy
from ..definitions import AgentDefinition, orchestrator_definition, specialist_definitions


@dataclass(frozen=True, slots=True)
class AgentChainBlueprint:
    """Inputs a concrete Deep Agents factory will bind for one agent."""

    definition: AgentDefinition
    context_policy: PhaseContextPolicy | None
    middleware_names: tuple[str, ...] = ("policy-context",)


class AgentChainFactory(Protocol):
    """Bootstrap-owned provider/model/tool compiler."""

    def create(self, blueprint: AgentChainBlueprint) -> object: ...


def build_chain_blueprints() -> dict[str, AgentChainBlueprint]:
    """Return stable chain metadata; no model or external client is created."""

    blueprints = {
        definition.name: AgentChainBlueprint(
            definition=definition,
            context_policy=get_policy(definition.name),
        )
        for definition in specialist_definitions()
    }
    orchestrator = orchestrator_definition()
    blueprints[orchestrator.name] = AgentChainBlueprint(
        definition=orchestrator,
        context_policy=None,
    )
    return blueprints


def build_chains(factory: AgentChainFactory) -> dict[str, object]:
    """Compile blueprints through an injected factory in deterministic order."""

    return {name: factory.create(blueprint) for name, blueprint in build_chain_blueprints().items()}
