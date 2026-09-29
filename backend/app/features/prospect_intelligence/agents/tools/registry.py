"""Auditable tool declarations; concrete handlers are injected in bootstrap."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    agents: tuple[str, ...]
    read_only: bool
    requires_review: bool = False


TOOL_REGISTRY: tuple[ToolSpec, ...] = (
    ToolSpec("get_crm_account", ("account-context",), True),
    ToolSpec("get_network_lanes", ("account-context",), True),
    ToolSpec("search_genlogs", ("external-research",), True),
    ToolSpec("search_sec", ("external-research",), True),
    ToolSpec("search_tavily", ("external-research",), True),
    ToolSpec("get_fmcsa", ("external-research",), True),
    ToolSpec("get_faf_market_volume", ("external-research",), True),
    ToolSpec("score_lane_fit_v1", ("lane-analyst",), True),
    ToolSpec("send_outreach", ("orchestrator",), False, requires_review=True),
)


def tools_for_agent(agent_name: str) -> tuple[ToolSpec, ...]:
    return tuple(spec for spec in TOOL_REGISTRY if agent_name in spec.agents)
