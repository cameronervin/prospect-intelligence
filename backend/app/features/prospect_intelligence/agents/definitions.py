"""Provider-neutral agent specifications; no model is created at import time."""

from dataclasses import dataclass
from typing import Protocol

from .prompts import SPECIALIST_PROMPTS
from .tools import tools_for_agent


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    name: str
    model: str
    instructions: str
    tools: tuple[str, ...]
    output_paths: tuple[str, ...]
    reasoning_effort: str | None = None


class AgentRuntimeFactory(Protocol):
    """Bootstrap-supplied factory for Deep Agents or a deterministic fake."""

    def create(self, definition: AgentDefinition) -> object: ...


@dataclass(frozen=True, slots=True)
class ConfiguredAgent:
    definition: AgentDefinition
    runtime: object


@dataclass(frozen=True, slots=True)
class AgentSuite:
    specialists: tuple[ConfiguredAgent, ...]
    orchestrator: ConfiguredAgent
    parallel_stage: tuple[str, ...]
    sequential_stage: tuple[str, ...]


def specialist_definitions() -> tuple[AgentDefinition, ...]:
    """Four-specialist MVP topology from the approved build plan."""

    read_only = ("read_file", "glob")
    return (
        AgentDefinition(
            name="account-context",
            model="gpt-6-luna",
            instructions=SPECIALIST_PROMPTS["account-context"],
            tools=(
                *read_only,
                "write_file",
                *(tool.name for tool in tools_for_agent("account-context")),
            ),
            output_paths=("/context/account.json", "/context/our_network.json"),
        ),
        AgentDefinition(
            name="external-research",
            model="gpt-6-luna",
            instructions=SPECIALIST_PROMPTS["external-research"],
            tools=(
                *read_only,
                "write_file",
                *(tool.name for tool in tools_for_agent("external-research")),
            ),
            output_paths=("/research/freight_intel/", "/research/company/", "/research/market/"),
        ),
        AgentDefinition(
            name="lane-analyst",
            model="gpt-6-luna",
            instructions=SPECIALIST_PROMPTS["lane-analyst"],
            tools=(
                *read_only,
                "write_file",
                *(tool.name for tool in tools_for_agent("lane-analyst")),
            ),
            output_paths=("/analysis/lane_fit.json", "/analysis/lane_fit.md"),
        ),
        AgentDefinition(
            name="outreach-drafter",
            model="gpt-6-luna",
            instructions=SPECIALIST_PROMPTS["outreach-drafter"],
            tools=(*read_only, "write_file"),
            output_paths=("/output/outreach_draft.md",),
        ),
    )


def orchestrator_definition() -> AgentDefinition:
    return AgentDefinition(
        name="orchestrator",
        model="gpt-6-sol",
        reasoning_effort="medium",
        instructions=SPECIALIST_PROMPTS["orchestrator"],
        tools=(
            "read_file",
            "glob",
            "write_file",
            "task",
            "write_todos",
            *(tool.name for tool in tools_for_agent("orchestrator")),
        ),
        output_paths=("/output/brief.md",),
    )


def build_agent_suite(factory: AgentRuntimeFactory) -> AgentSuite:
    specialists = tuple(
        ConfiguredAgent(definition=definition, runtime=factory.create(definition))
        for definition in specialist_definitions()
    )
    orchestrator_spec = orchestrator_definition()
    orchestrator = ConfiguredAgent(
        definition=orchestrator_spec,
        runtime=factory.create(orchestrator_spec),
    )
    return AgentSuite(
        specialists=specialists,
        orchestrator=orchestrator,
        parallel_stage=("account-context", "external-research"),
        sequential_stage=("lane-analyst", "outreach-drafter"),
    )
