"""Compose the exact tool registry exposed through agent specifications."""

from collections.abc import Sequence

from langchain_core.tools import BaseTool

from .artifacts import (
    materialize_account_context,
    materialize_external_research,
    score_lane_fit_v1,
    submit_outreach_draft,
    submit_quality_review,
)
from .sources import (
    get_crm_account,
    get_faf_market_volume,
    get_fmcsa,
    get_network_lanes,
    search_genlogs,
    search_sec,
    search_tavily,
)
from .workflow import send_outreach


class ToolRegistry:
    def __init__(self, tools: Sequence[BaseTool]) -> None:
        self._tools = {item.name: item for item in tools}

    def resolve(self, names: Sequence[str]) -> tuple[BaseTool, ...]:
        missing = sorted(set(names).difference(self._tools))
        if missing:
            raise ValueError(f"agent spec references unknown tools: {missing}")
        return tuple(self._tools[name] for name in names)


def build_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        (
            get_crm_account,
            get_network_lanes,
            search_genlogs,
            search_sec,
            search_tavily,
            get_fmcsa,
            get_faf_market_volume,
            materialize_account_context,
            materialize_external_research,
            score_lane_fit_v1,
            submit_quality_review,
            submit_outreach_draft,
            send_outreach,
        )
    )
