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

from app.features.prospect_intelligence.agents.compiler import build_prospect_agent_runtime
from app.features.prospect_intelligence.contracts.agent_runtime import (
    ProspectAgentInput,
    ProspectRuntimeContext,
)
from app.features.prospect_intelligence.contracts.filesystem import PROSPECT_FILES
from evaluation.contracts.snapshot import decode_artifacts, normalize_snapshot
from evaluation.targets.scenario import scenario_artifacts
from evaluation.targets.scripted_model import ScenarioScriptedModel

__all__ = ["ProspectOfflineTarget", "decode_artifacts", "normalize_snapshot"]


def _trajectory(raw: Mapping[str, object]) -> list[str]:
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
    events: list[str] = []
    event_names = {
        "account-context": "account_context.completed",
        "external-research": "external_research.completed",
        "lane-analyst": "lane_analyst.completed",
        "outreach-drafter": "outreach_drafter.completed",
    }
    for name, args in calls:
        if name == "task" and isinstance(args.get("subagent_type"), str):
            event = event_names.get(cast(str, args["subagent_type"]))
            if event is not None:
                events.append(event)
        elif name == "send_outreach":
            events.append("review.requested")
    return events


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

        scripted = ScenarioScriptedModel(artifacts=scenario_artifacts(inputs))
        runtime = build_prospect_agent_runtime(
            orchestrator_model=scripted,
            specialist_model=scripted,
            checkpointer=InMemorySaver(),
            store=InMemoryStore(),
        )
        context = ProspectRuntimeContext(
            run_id=uuid5(NAMESPACE_URL, f"cam-38:{example_id}"),
            tenant_id="evaluation",
            rep_id="runner",
        )
        started = perf_counter()
        with tracing_context(enabled=False):
            result = await runtime.execute(
                ProspectAgentInput(
                    account_id=cast(str, account_id),
                    task_brief=f"Evaluate synthetic freight fit for {account_name}.",
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
            trajectory_events=_trajectory(result.raw),
            tool_calls=tool_calls,
            pending_review=result.pending_interrupt == "send_outreach",
            latency_seconds=perf_counter() - started,
            account_name=cast(str, account_name),
            rep_preferences=context.rep_preferences,
        ).to_outputs()
