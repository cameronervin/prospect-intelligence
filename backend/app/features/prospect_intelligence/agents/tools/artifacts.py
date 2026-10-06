"""Typed tools that validate and materialize machine-consumed artifacts."""

import asyncio
from collections.abc import Mapping
from typing import Annotated, cast

from deepagents.backends.protocol import FileData
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict, Field

from ...contracts.agent_runtime import ProspectRuntimeContext
from ...contracts.filesystem import PROSPECT_FILES
from ...contracts.lane_analysis import LaneAnalysisArtifact
from ...contracts.models import FitVerdict, OutreachDraft
from ...contracts.review import QualityReviewArtifact
from ...contracts.source_serialization import (
    canonical_json,
    canonical_source_document,
    canonical_source_json,
    combined_source_document,
    market_source_document,
)
from ...domain.errors import AgentOutputInvalidError
from ...domain.outreach import OutreachContext, customer_outreach_issues
from ..context import current_runtime_context
from ..guardrails.deterministic import artifact_content, validate_outreach
from ..state import ProspectDeepAgentState
from ._support import invoke_handler, materialized_files


@tool(
    "materialize_account_context",
    description="Retrieve trusted account and network context and write both canonical files.",
)
async def materialize_account_context(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> Command[object]:
    account, network = await asyncio.gather(
        invoke_handler("get_crm_account", {}, runtime),
        invoke_handler("get_network_lanes", {}, runtime),
    )
    return materialized_files(
        runtime,
        {
            PROSPECT_FILES.account_context: canonical_source_json(account),
            PROSPECT_FILES.network_context: canonical_source_json(network),
        },
    )


def _market_queries(freight: object) -> tuple[tuple[str, str], ...]:
    value = canonical_source_document(freight).get("value")
    if value is None:
        return ()
    if not isinstance(value, Mapping):
        raise TypeError("freight source value must be an object")
    raw_queries = cast("Mapping[object, object]", value).get("market_queries", [])
    if not isinstance(raw_queries, list):
        raise TypeError("freight market_queries must be a list")
    queries: list[tuple[str, str]] = []
    for raw in cast("list[object]", raw_queries):
        if not isinstance(raw, Mapping):
            raise TypeError("freight market query must be an object")
        query = cast("Mapping[object, object]", raw)
        origin, destination = query.get("origin_zone"), query.get("destination_zone")
        if not isinstance(origin, str) or not isinstance(destination, str):
            raise TypeError("freight market query zones must be strings")
        queries.append((origin, destination))
    return tuple(queries)


@tool(
    "materialize_external_research",
    description="Collect reviewed public sources and write all canonical research files.",
)
async def materialize_external_research(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> Command[object]:
    freight = await invoke_handler("search_genlogs", {}, runtime)
    sec, web, carrier = await asyncio.gather(
        invoke_handler("search_sec", {}, runtime),
        invoke_handler("search_tavily", {}, runtime),
        invoke_handler("get_fmcsa", {}, runtime),
    )
    market_results = [
        (
            f"{origin}->{destination}",
            await invoke_handler(
                "get_faf_market_volume",
                {"origin_zone": origin, "destination_zone": destination},
                runtime,
            ),
        )
        for origin, destination in _market_queries(freight)
    ]
    market_document: dict[str, object] = (
        market_source_document(market_results)
        if market_results
        else cast(
            "dict[str, object]",
            {
                "sources": {},
                "coverage": [
                    {
                        "source": "FAF5 market data",
                        "status": "unavailable",
                        "detail": "no reviewed market queries",
                    }
                ],
                "evidence": [],
            },
        )
    )
    return materialized_files(
        runtime,
        {
            PROSPECT_FILES.freight_research: canonical_source_json(freight),
            PROSPECT_FILES.company_research: canonical_json(
                combined_source_document((sec, web, carrier))
            ),
            PROSPECT_FILES.market_research: canonical_json(market_document),
        },
    )


@tool(
    "score_lane_fit_v1",
    description="Apply deterministic lane_fit_v1 scoring to freight and network evidence.",
)
async def score_lane_fit_v1(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> Command[object]:
    raw = await invoke_handler("score_lane_fit_v1", {}, runtime)
    if not isinstance(raw, Mapping):
        raise TypeError("lane score handler must return an object")
    content = canonical_json(
        {str(key): value for key, value in cast("Mapping[object, object]", raw).items()}
    )
    LaneAnalysisArtifact.from_json(content)
    return materialized_files(runtime, {PROSPECT_FILES.lane_fit_json: content})


class ReviewFindingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128)
    file: str = Field(min_length=1, max_length=16)
    category: str = Field(min_length=1, max_length=64)
    severity: str = Field(min_length=1, max_length=16)
    excerpt: str = Field(min_length=1, max_length=512)
    problem: str = Field(min_length=1, max_length=512)
    required_change: str = Field(min_length=1, max_length=512)


@tool(
    "submit_quality_review",
    description="Validate typed quality findings and write the canonical review artifact.",
)
def submit_quality_review(
    round: int,
    verdict: str,
    findings: list[ReviewFindingInput],
    resolved_prior: list[str],
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> Command[object]:
    payload: dict[str, object] = {
        "round": round,
        "verdict": verdict,
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "resolved_prior": resolved_prior,
    }
    content = canonical_json(payload)
    try:
        QualityReviewArtifact.from_json(content)
    except ValueError:
        raise AgentOutputInvalidError("review_contract_invalid") from None
    return materialized_files(runtime, {PROSPECT_FILES.review_findings: content})


@tool(
    "submit_outreach_draft",
    description="Validate four typed customer-safe paragraphs and write the outreach draft.",
)
def submit_outreach_draft(
    subject: Annotated[
        str,
        "Customer-safe subject that includes the selected account name; no digits or markup.",
    ],
    greeting: Annotated[str, "Exactly: Hi <selected contact first name>,"],
    introduction: Annotated[
        str,
        (
            "Name the selected representative and say they represent an asset-based truckload "
            "carrier without inventing a carrier brand."
        ),
    ],
    relevance: Annotated[
        str,
        (
            "Evidence-grounded relevance that includes the top lane exactly as "
            "<ORIGIN>-to-<DESTINATION>."
        ),
    ],
    call_to_action: Annotated[
        str,
        "A specific, low-friction question of at least five words that ends with a question mark.",
    ],
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> Command[object]:
    files = cast("Mapping[str, FileData]", runtime.state.get("files", {}))
    context = current_runtime_context(runtime.context)
    analysis = LaneAnalysisArtifact.from_json(
        artifact_content(files[PROSPECT_FILES.lane_fit_json], PROSPECT_FILES.lane_fit_json)
    )
    if analysis.verdict is not FitVerdict.FIT or not analysis.top_lanes:
        raise ValueError("fit lane required")
    lane = analysis.top_lanes[0]
    draft = OutreachDraft(
        subject=subject,
        body="\n\n".join((greeting, introduction, relevance, call_to_action)),
    )
    outreach_scope = OutreachContext(
        account_name=context.account_name,
        contact_name=context.contact_name,
        contact_role=context.contact_role,
        rep_display_name=context.rep_display_name,
        origin=lane.origin,
        destination=lane.destination,
        other_account_names=context.other_account_names,
    )
    issues = customer_outreach_issues(draft, outreach_scope)
    if issues:
        raise AgentOutputInvalidError(*(issue.value for issue in issues))
    content = f"Subject: {draft.subject}\n\n{draft.body}"
    validate_outreach(content, files, outreach_scope)
    return materialized_files(runtime, {PROSPECT_FILES.outreach_draft: content})
