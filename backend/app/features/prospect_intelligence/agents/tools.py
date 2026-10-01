"""Decorated feature tools and their exact per-agent registry."""

import asyncio
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import cast
from uuid import UUID

from deepagents.backends.protocol import FileData
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.types import Command

from ..contracts.agent_runtime import ProgressSignal, ProspectRuntimeContext
from ..contracts.citations import evidence_citation_id
from ..contracts.filesystem import PROSPECT_FILES
from ..contracts.models import Evidence
from .context import current_runtime_context, current_step
from .guardrails.deterministic import validate_workflow_artifacts
from .state import ProspectDeepAgentState


def _json_safe(value: object) -> object:
    if isinstance(value, Evidence):
        provenance = cast("dict[str, object]", asdict(value.provenance))
        safe_provenance = cast("Mapping[str, object]", _json_safe(provenance))
        return {
            "claim": value.claim,
            "citation_id": evidence_citation_id(safe_provenance),
            "provenance": safe_provenance,
        }
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(cast("dict[object, object]", asdict(value)))
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in cast("Mapping[object, object]", value).items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in cast("Iterable[object]", value)]
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"tool result contains unsupported value: {type(value).__name__}")


async def _invoke_source(
    name: str,
    payload: dict[str, object],
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> str:
    context = current_runtime_context(runtime.context)
    handler = context.tool_handlers.get(name)
    if handler is None:
        raise RuntimeError(f"tool handler is unavailable: {name}")
    step = current_step()
    try:
        result = await asyncio.to_thread(handler, payload)
    except Exception:
        if context.progress is not None and step is not None:
            await context.progress(ProgressSignal("source", step, failed=True, tool_name=name))
        raise RuntimeError(
            "The read-only source is unavailable; record degraded coverage."
        ) from None
    if context.progress is not None and step is not None:
        await context.progress(ProgressSignal("source", step, tool_name=name))
    return json.dumps(_json_safe(result), sort_keys=True, separators=(",", ":"))


@tool("get_crm_account", description="Retrieve the tenant-scoped CRM account for this run.")
async def get_crm_account(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> str:
    return await _invoke_source("get_crm_account", {}, runtime)


@tool("get_network_lanes", description="Retrieve the carrier network lanes available to this run.")
async def get_network_lanes(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> str:
    return await _invoke_source("get_network_lanes", {}, runtime)


@tool("search_genlogs", description="Retrieve normalized freight activity for the prospect.")
async def search_genlogs(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> str:
    return await _invoke_source("search_genlogs", {}, runtime)


@tool("search_sec", description="Search SEC company evidence for the prospect.")
async def search_sec(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> str:
    return await _invoke_source("search_sec", {}, runtime)


@tool("search_tavily", description="Search public web evidence for the prospect company.")
async def search_tavily(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> str:
    return await _invoke_source("search_tavily", {}, runtime)


@tool(
    "get_fmcsa",
    description="Look up an FMCSA carrier by USDOT number, legal name, or both.",
)
async def get_fmcsa(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
    usdot_number: str | None = None,
    legal_name: str | None = None,
) -> str:
    payload: dict[str, object] = {
        key: value
        for key, value in {"usdot_number": usdot_number, "legal_name": legal_name}.items()
        if value is not None
    }
    return await _invoke_source(
        "get_fmcsa",
        payload,
        runtime,
    )


@tool(
    "get_faf_market_volume",
    description="Retrieve FAF market volume for one origin and destination zone pair.",
)
async def get_faf_market_volume(
    origin_zone: str,
    destination_zone: str,
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> str:
    return await _invoke_source(
        "get_faf_market_volume",
        {"origin_zone": origin_zone, "destination_zone": destination_zone},
        runtime,
    )


@tool(
    "score_lane_fit_v1",
    description="Apply deterministic lane_fit_v1 scoring to freight and network evidence.",
)
async def score_lane_fit_v1(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> str:
    return await _invoke_source("score_lane_fit_v1", {}, runtime)


@tool("send_outreach", description="Submit the completed outreach draft for human review.")
def send_outreach(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> Command[object]:
    files = cast("Mapping[str, FileData]", runtime.state.get("files", {}))
    context = current_runtime_context(runtime.context)
    validate_workflow_artifacts(
        files,
        allowed_memory_path=PROSPECT_FILES.rep_memory(context.tenant_id, context.rep_id),
    )
    return Command(
        update={
            "review_requested": {"name": "send_outreach"},
            "messages": [
                ToolMessage(
                    content="Outreach is ready for human review.",
                    tool_call_id=runtime.tool_call_id or "send_outreach",
                )
            ],
        }
    )


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
            score_lane_fit_v1,
            send_outreach,
        )
    )
