"""Credential-free target that executes the real compiled prospect graph."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from time import perf_counter
from typing import cast
from uuid import NAMESPACE_URL, uuid5

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langsmith import tracing_context  # pyright: ignore[reportUnknownVariableType]

from app.features.authentication.public import AuthContext, UserRole
from app.features.prospect_intelligence.agents.compiler import build_prospect_agent_runtime
from app.features.prospect_intelligence.contracts.agent_runtime import (
    ProspectAgentInput,
    ProspectRuntimeContext,
    ToolHandler,
)
from app.features.prospect_intelligence.contracts.filesystem import PROSPECT_FILES
from evaluation.contracts.snapshot import decode_artifacts, normalize_snapshot
from evaluation.targets.scenario import scenario_artifacts
from evaluation.targets.scenario_identity import synthetic_v2_identity
from evaluation.targets.scripted_model import ScenarioScriptedModel

__all__ = [
    "ProspectOfflineTarget",
    "decode_artifacts",
    "normalize_snapshot",
    "tool_call_names",
    "trajectory_events",
]


def _raw_tool_calls(raw: Mapping[str, object]) -> list[tuple[str, Mapping[str, object]]]:
    messages = raw.get("messages")
    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)):
        return []
    calls: list[tuple[str, Mapping[str, object]]] = []
    for message in cast("Sequence[object]", messages):
        if isinstance(message, AIMessage):
            calls.extend(
                (call["name"], cast("Mapping[str, object]", call["args"]))
                for call in message.tool_calls
            )
    return calls


def tool_call_names(raw: Mapping[str, object]) -> list[str]:
    """Return sanitized tool names visible in the root graph messages."""

    return [name for name, _args in _raw_tool_calls(raw)]


def trajectory_events(raw: Mapping[str, object]) -> list[str]:
    calls = _raw_tool_calls(raw)
    events: list[str] = []
    event_names = {
        "account-context": "account_context.completed",
        "external-research": "external_research.completed",
        "lane-analyst": "lane_analyst.completed",
        "outreach-drafter": "outreach_drafter.completed",
        "quality-reviewer": "quality_review.completed",
    }
    for name, args in calls:
        if name == "task" and isinstance(args.get("subagent_type"), str):
            event = event_names.get(cast(str, args["subagent_type"]))
            if event is not None:
                events.append(event)
        elif name == "send_outreach":
            events.append("review.requested")
    return events


def _source_result(content: str) -> dict[str, object]:
    """Rehydrate a canonical fixture artifact as a normalized source result."""

    raw = cast(object, json.loads(content))
    if not isinstance(raw, dict):
        raise ValueError("scenario source artifact must be an object")
    document = cast("dict[str, object]", raw)
    coverage = document.pop("coverage", None)
    evidence = document.pop("evidence", None)
    if not isinstance(coverage, dict) or not isinstance(evidence, list):
        raise ValueError("scenario source artifact is missing source metadata")
    return {"value": document, "coverage": coverage, "evidence": evidence}


def _tool_handlers(artifacts: Mapping[str, str]) -> dict[str, ToolHandler]:
    account = _source_result(artifacts[PROSPECT_FILES.account_context])
    network = _source_result(artifacts[PROSPECT_FILES.network_context])
    freight = _source_result(artifacts[PROSPECT_FILES.freight_research])
    company = _source_result(artifacts[PROSPECT_FILES.company_research])
    market = _source_result(artifacts[PROSPECT_FILES.market_research])
    analysis = json.loads(artifacts[PROSPECT_FILES.lane_fit_json])
    return {
        "get_crm_account": lambda _: account,
        "get_network_lanes": lambda _: network,
        "search_genlogs": lambda _: freight,
        "search_sec": lambda _: company,
        "search_tavily": lambda _: company,
        "get_fmcsa": lambda _: company,
        "get_faf_market_volume": lambda _: market,
        "score_lane_fit_v1": lambda _: analysis,
    }


class ProspectOfflineTarget:
    """LangSmith-compatible target over the compiled graph."""

    def __call__(self, inputs: dict[str, object]) -> dict[str, object]:
        return asyncio.run(self.ainvoke(inputs))

    async def ainvoke(self, inputs: Mapping[str, object]) -> dict[str, object]:
        required = {"example_id", "account_id", "account_name", "input_payload"}
        if required.difference(inputs):
            raise ValueError("offline target inputs are incomplete")
        example_id, account_id, account_name = (
            inputs["example_id"],
            inputs["account_id"],
            inputs["account_name"],
        )
        if not all(
            isinstance(item, str) and item for item in (example_id, account_id, account_name)
        ):
            raise ValueError("offline target identifiers must be non-empty strings")
        if not isinstance(inputs["input_payload"], Mapping):
            raise ValueError("offline target input_payload must be an object")

        identity = synthetic_v2_identity(inputs)
        artifacts = scenario_artifacts(inputs)
        analysis = cast(
            "dict[str, object]",
            json.loads(artifacts[PROSPECT_FILES.lane_fit_json]),
        )
        raw_lanes = analysis.get("top_lanes", [])
        if not isinstance(raw_lanes, list):
            raise ValueError("offline target lane analysis is invalid")
        outreach_context = None
        if raw_lanes:
            lane = cast("Mapping[str, object]", raw_lanes[0])
            outreach_context = identity.outreach_context(
                str(lane["origin"]), str(lane["destination"])
            )
        scripted = ScenarioScriptedModel(
            artifacts=artifacts,
            outreach_context=outreach_context,
        )
        runtime = build_prospect_agent_runtime(
            orchestrator_model=scripted,
            specialist_model=scripted,
            checkpointer=InMemorySaver(),
            store=InMemoryStore(),
        )
        context = ProspectRuntimeContext(
            run_id=uuid5(NAMESPACE_URL, f"cam-38:{example_id}"),
            auth=AuthContext(
                subject="evaluation-runner",
                tenant_id="evaluation",
                rep_id="runner",
                roles=frozenset({UserRole.SALES_REP}),
            ),
            account_name=identity.account_name,
            contact_name=identity.contact_name,
            contact_role=identity.contact_role,
            rep_display_name=identity.rep_display_name,
            tool_handlers=_tool_handlers(artifacts),
        )
        started = perf_counter()
        with tracing_context(enabled=False):
            result = await runtime.execute(
                ProspectAgentInput(
                    account_id=cast(str, account_id),
                    task_brief="Evaluate the selected synthetic account's freight fit.",
                ),
                context=context,
            )
        all_artifacts = decode_artifacts(result.files)
        analysis = cast(
            "dict[str, object]",
            json.loads(all_artifacts[PROSPECT_FILES.lane_fit_json]),
        )
        tool_calls = tuple(scripted.tool_call_names)
        return normalize_snapshot(
            files=result.files,
            analysis=analysis,
            trajectory_events=trajectory_events(result.raw),
            tool_calls=tool_calls,
            pending_review=result.pending_interrupt == "send_outreach",
            latency_seconds=perf_counter() - started,
            account_name=identity.account_name,
            rep_preferences=context.rep_preferences,
        ).to_outputs()
