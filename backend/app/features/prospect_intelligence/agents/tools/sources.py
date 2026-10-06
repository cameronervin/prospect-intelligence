"""Read-only source tools retained for explicit registry resolution."""

from langchain.tools import ToolRuntime, tool

from ...contracts.agent_runtime import ProspectRuntimeContext
from ...contracts.source_serialization import normalized_json
from ..state import ProspectDeepAgentState
from ._support import invoke_handler


@tool("get_crm_account", description="Retrieve the tenant-scoped CRM account for this run.")
async def get_crm_account(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> str:
    return normalized_json(await invoke_handler("get_crm_account", {}, runtime))


@tool("get_network_lanes", description="Retrieve the carrier network lanes available to this run.")
async def get_network_lanes(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> str:
    return normalized_json(await invoke_handler("get_network_lanes", {}, runtime))


@tool("search_genlogs", description="Retrieve normalized freight activity for the prospect.")
async def search_genlogs(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> str:
    return normalized_json(await invoke_handler("search_genlogs", {}, runtime))


@tool("search_sec", description="Search SEC company evidence for the prospect.")
async def search_sec(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> str:
    return normalized_json(await invoke_handler("search_sec", {}, runtime))


@tool("search_tavily", description="Search public web evidence for the prospect company.")
async def search_tavily(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> str:
    return normalized_json(await invoke_handler("search_tavily", {}, runtime))


@tool(
    "get_fmcsa",
    description="Look up FMCSA context for the selected prospect account.",
)
async def get_fmcsa(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> str:
    return normalized_json(await invoke_handler("get_fmcsa", {}, runtime))


@tool(
    "get_faf_market_volume",
    description="Retrieve FAF market volume for one origin and destination zone pair.",
)
async def get_faf_market_volume(
    origin_zone: str,
    destination_zone: str,
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> str:
    return normalized_json(
        await invoke_handler(
            "get_faf_market_volume",
            {"origin_zone": origin_zone, "destination_zone": destination_zone},
            runtime,
        )
    )
