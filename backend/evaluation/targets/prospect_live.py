"""Hosted prospect target over the real graph with synthetic-only source handlers."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import cast
from uuid import uuid4

from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langsmith import tracing_context  # pyright: ignore[reportUnknownVariableType]
from langsmith.run_helpers import set_run_metadata

from app.features.authentication.public import AuthContext, UserRole
from app.features.prospect_intelligence.agents.compiler import build_prospect_agent_runtime
from app.features.prospect_intelligence.contracts.agent_runtime import (
    ProspectAgentInput,
    ProspectRuntimeContext,
    ToolHandler,
)
from app.features.prospect_intelligence.contracts.filesystem import PROSPECT_FILES
from evaluation.contracts.snapshot import decode_artifacts, normalize_snapshot
from evaluation.datasets import langsmith_examples
from evaluation.targets.prospect_graph import tool_call_names, trajectory_events
from evaluation.targets.scenario import scenario_artifacts
from evaluation.targets.scenario_identity import synthetic_v2_identity


@dataclass(frozen=True, slots=True)
class ModelTokenPrice:
    input: float
    cached_input: float
    output: float


STANDARD_MODEL_PRICES: Mapping[str, ModelTokenPrice] = {
    "gpt-5.6-sol": ModelTokenPrice(input=4.0, cached_input=0.4, output=20.0),
    "gpt-5.6-luna": ModelTokenPrice(input=0.2, cached_input=0.02, output=1.2),
}


def _non_negative_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"usage {field} must be a non-negative integer")
    return value


def _model_price(model: str, prices: Mapping[str, ModelTokenPrice]) -> ModelTokenPrice:
    matches = [name for name in prices if model == name or model.startswith(f"{name}-")]
    if not matches:
        raise ValueError(f"pricing is unavailable for model: {model}")
    return prices[max(matches, key=len)]


def usage_cost_usd(
    usage: Mapping[str, Mapping[str, object]],
    prices: Mapping[str, ModelTokenPrice] = STANDARD_MODEL_PRICES,
) -> float:
    """Calculate target cost from provider-reported aggregate token usage."""

    total = 0.0
    for model, counts in usage.items():
        price = _model_price(model, prices)
        input_tokens = _non_negative_int(counts.get("input_tokens", 0), field="input_tokens")
        output_tokens = _non_negative_int(counts.get("output_tokens", 0), field="output_tokens")
        details = counts.get("input_token_details", {})
        if not isinstance(details, Mapping):
            raise ValueError("usage input_token_details must be an object")
        token_details = cast("Mapping[str, object]", details)
        cached = _non_negative_int(token_details.get("cache_read", 0), field="cache_read")
        if cached > input_tokens:
            raise ValueError("cached input tokens cannot exceed input tokens")
        total += (
            (input_tokens - cached) * price.input
            + cached * price.cached_input
            + output_tokens * price.output
        ) / 1_000_000
    return total


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"live target {field} must be an object")
    return cast("Mapping[str, object]", value)


def _handlers(payload: Mapping[str, object]) -> Mapping[str, ToolHandler]:
    generated = scenario_artifacts({"input_payload": payload})

    def artifact(path: str) -> object:
        return json.loads(generated[path])

    crm = artifact(PROSPECT_FILES.account_context)
    network = artifact(PROSPECT_FILES.network_context)
    freight = artifact(PROSPECT_FILES.freight_research)
    company = artifact(PROSPECT_FILES.company_research)
    market = artifact(PROSPECT_FILES.market_research)
    analysis = artifact(PROSPECT_FILES.lane_fit_json)

    def constant(value: object) -> Callable[[dict[str, object]], object]:
        return lambda _request: value

    return {
        "get_crm_account": constant(crm),
        "get_network_lanes": constant(network),
        "search_genlogs": constant(freight),
        "search_sec": constant(company),
        "search_tavily": constant(company),
        "get_fmcsa": constant(company),
        "get_faf_market_volume": constant(market),
        "score_lane_fit_v1": constant(analysis),
    }


class ProspectLiveTarget:
    """LangSmith target using real models without any live business-data integrations."""

    def __init__(
        self,
        orchestrator_model: BaseChatModel,
        specialist_model: BaseChatModel,
        *,
        prompt_revision: str = "outreach-v2",
        interpreter_enabled: bool = True,
        prices: Mapping[str, ModelTokenPrice] = STANDARD_MODEL_PRICES,
    ) -> None:
        if prompt_revision != "outreach-v2":
            raise ValueError("active live targets require prompt revision outreach-v2")
        self._runtime = build_prospect_agent_runtime(
            orchestrator_model=orchestrator_model,
            specialist_model=specialist_model,
            checkpointer=InMemorySaver(),
            store=InMemoryStore(),
            prompt_revision=prompt_revision,
            interpreter_enabled=interpreter_enabled,
        )
        self._prices = prices
        self._canonical_inputs = {
            cast(str, inputs["example_id"]): dict(inputs)
            for example in langsmith_examples()
            if (inputs := example.inputs) is not None
        }

    def __call__(self, inputs: dict[str, object]) -> dict[str, object]:
        return asyncio.run(self.ainvoke(inputs))

    async def ainvoke(self, inputs: Mapping[str, object]) -> dict[str, object]:
        required = {"example_id", "account_id", "account_name", "input_payload"}
        if required.difference(inputs):
            raise ValueError("live target inputs are incomplete")
        supplied_example_id = inputs["example_id"]
        if not isinstance(supplied_example_id, str) or self._canonical_inputs.get(
            supplied_example_id
        ) != dict(inputs):
            raise ValueError("live target inputs must match the canonical synthetic dataset")
        example_id, account_id, account_name = (
            inputs["example_id"],
            inputs["account_id"],
            inputs["account_name"],
        )
        if not all(
            isinstance(item, str) and item for item in (example_id, account_id, account_name)
        ):
            raise ValueError("live target identifiers must be non-empty strings")
        payload = _mapping(inputs["input_payload"], field="input_payload")
        identity = synthetic_v2_identity(inputs)
        rep_id_hash = hashlib.sha256(f"cam-40:{example_id}".encode()).hexdigest()
        context = ProspectRuntimeContext(
            run_id=uuid4(),
            auth=AuthContext(
                subject=rep_id_hash,
                tenant_id="evaluation",
                rep_id=rep_id_hash,
                roles=frozenset({UserRole.SALES_REP}),
            ),
            tool_handlers=_handlers(payload),
            account_name=identity.account_name,
            contact_name=identity.contact_name,
            contact_role=identity.contact_role,
            rep_display_name=identity.rep_display_name,
        )
        set_run_metadata(rep_id_hash=rep_id_hash)
        started = perf_counter()
        with (
            tracing_context(metadata={"rep_id_hash": rep_id_hash}),
            get_usage_metadata_callback() as usage_callback,
        ):
            try:
                result = await self._runtime.execute(
                    ProspectAgentInput(
                        account_id=cast(str, account_id),
                        task_brief="Evaluate the selected synthetic account's freight fit.",
                    ),
                    context=context,
                )
                latency_seconds = perf_counter() - started
                artifacts = decode_artifacts(result.files)
                analysis = _mapping(
                    json.loads(artifacts[PROSPECT_FILES.lane_fit_json]),
                    field="lane analysis",
                )
                usage = cast("Mapping[str, Mapping[str, object]]", usage_callback.usage_metadata)
                outputs = normalize_snapshot(
                    files=result.files,
                    analysis=analysis,
                    trajectory_events=trajectory_events(result.raw),
                    tool_calls=tool_call_names(result.raw),
                    pending_review=result.pending_interrupt == "send_outreach",
                    latency_seconds=latency_seconds,
                    account_name=identity.account_name,
                    semantic_source_artifacts={
                        path: body
                        for path, body in scenario_artifacts({"input_payload": payload}).items()
                        if path.startswith(("/context/", "/research/"))
                    },
                    allowed_memory_path=PROSPECT_FILES.rep_memory("evaluation", rep_id_hash),
                ).to_outputs()
                outputs["cost_usd"] = usage_cost_usd(usage, self._prices)
                outputs["token_usage"] = {model: dict(counts) for model, counts in usage.items()}
                outputs["run_metadata"] = {"rep_id_hash": rep_id_hash}
                return outputs
            except Exception as error:
                usage = cast("Mapping[str, Mapping[str, object]]", usage_callback.usage_metadata)
                return {
                    "artifacts": {},
                    "artifact_observations": {},
                    "semantic_observations": {},
                    "analysis": {},
                    "verdict": "",
                    "trajectory_events": [],
                    "tool_calls": [],
                    "pending_review": False,
                    "latency_seconds": perf_counter() - started,
                    "cost_usd": usage_cost_usd(usage, self._prices),
                    "tool_call_count": 0,
                    "token_usage": {model: dict(counts) for model, counts in usage.items()},
                    "run_metadata": {
                        "rep_id_hash": rep_id_hash,
                        "status": "target_error",
                        "error_type": type(error).__name__,
                    },
                }
