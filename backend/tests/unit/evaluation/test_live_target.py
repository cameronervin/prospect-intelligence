"""Hosted target composes the real graph around synthetic, sanitized inputs."""

import hashlib
from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
from typing import cast

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage

from app.features.prospect_intelligence.contracts.agent_runtime import (
    ProspectAgentResult,
    ProspectRuntimeContext,
)
from app.features.prospect_intelligence.public import PROSPECT_FILES
from evaluation.datasets import langsmith_examples
from evaluation.experiments.hosted import runtime as hosted_runtime
from evaluation.targets import prospect_live as live_target
from evaluation.targets.prospect_live import ModelTokenPrice, ProspectLiveTarget, usage_cost_usd
from tests.unit.prospect_intelligence.agent_test_support import completed_files


@pytest.mark.asyncio
async def test_owned_hosted_target_closes_runtime_with_async_close() -> None:
    class FakeRuntime:
        closed = False

        async def close(self) -> None:
            self.closed = True

    class FakeTarget:
        async def ainvoke(self, inputs: Mapping[str, object]) -> Mapping[str, object]:
            return inputs

    runtime = FakeRuntime()
    target = hosted_runtime._OwnedTarget(  # pyright: ignore[reportPrivateUsage]
        FakeTarget(), runtime
    )

    await target.aclose()

    assert runtime.closed is True


def test_usage_cost_accounts_for_cached_input_by_model() -> None:
    usage = {
        "gpt-5.6-sol-2026-09-01": {
            "input_tokens": 1_000,
            "output_tokens": 100,
            "total_tokens": 1_100,
            "input_token_details": {"cache_read": 250},
        },
        "gpt-5.6-luna": {
            "input_tokens": 2_000,
            "output_tokens": 200,
            "total_tokens": 2_200,
        },
    }
    prices = {
        "gpt-5.6-sol": ModelTokenPrice(input=4.0, cached_input=0.4, output=20.0),
        "gpt-5.6-luna": ModelTokenPrice(input=0.2, cached_input=0.02, output=1.2),
    }

    assert usage_cost_usd(usage, prices) == pytest.approx(0.00574)


def test_usage_cost_rejects_unpriced_models() -> None:
    usage = {"unknown": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}
    with pytest.raises(ValueError, match="pricing"):
        usage_cost_usd(usage, {})


@pytest.mark.asyncio
async def test_live_target_uses_synthetic_handlers_and_hashes_rep_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contexts: list[ProspectRuntimeContext] = []
    build_options: list[dict[str, object]] = []
    trace_metadata: list[Mapping[str, object]] = []
    run_metadata: list[Mapping[str, object]] = []

    class FakeRuntime:
        async def execute(
            self,
            input: object,
            *,
            context: ProspectRuntimeContext,
        ) -> ProspectAgentResult:
            del input
            contexts.append(context)
            assert (
                cast("Mapping[str, object]", context.tool_handlers["get_crm_account"]({}))[
                    "account_name"
                ]
                == "Synthetic Core Shipper One"
            )
            for name in (
                "get_crm_account",
                "get_network_lanes",
                "search_genlogs",
                "search_sec",
                "search_tavily",
                "get_fmcsa",
                "get_faf_market_volume",
            ):
                source = cast("Mapping[str, object]", context.tool_handlers[name]({}))
                assert isinstance(source["coverage"], Mapping)
                evidence = cast("list[Mapping[str, object]]", source["evidence"])
                provenance = cast("Mapping[str, object]", evidence[0]["provenance"])
                assert set(provenance) == {
                    "source",
                    "mode",
                    "endpoint_or_artifact",
                    "retrieved_at",
                    "evidence_location",
                    "source_version",
                }
            files = completed_files()
            files[PROSPECT_FILES.rep_memory("evaluation", context.rep_id)] = {
                "content": "# Synthetic rep preferences\n",
                "encoding": "utf-8",
            }
            return ProspectAgentResult(
                files=files,
                completed_stages=(),
                pending_interrupt="send_outreach",
                raw={
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "task",
                                    "args": {"subagent_type": "account-context"},
                                    "id": "delegate",
                                    "type": "tool_call",
                                },
                                {
                                    "name": "send_outreach",
                                    "args": {},
                                    "id": "review",
                                    "type": "tool_call",
                                },
                            ],
                        )
                    ]
                },
            )

    def fake_build(**kwargs: object) -> FakeRuntime:
        build_options.append(dict(kwargs))
        return FakeRuntime()

    def fake_set_run_metadata(**metadata: object) -> None:
        run_metadata.append(metadata)

    @contextmanager
    def fake_tracing_context(**kwargs: object):  # type: ignore[no-untyped-def]
        trace_metadata.append(cast("Mapping[str, object]", kwargs["metadata"]))
        yield

    monkeypatch.setattr(live_target, "build_prospect_agent_runtime", fake_build)
    monkeypatch.setattr(live_target, "tracing_context", fake_tracing_context)
    monkeypatch.setattr(
        live_target,
        "set_run_metadata",
        fake_set_run_metadata,
        raising=False,
    )
    model = FakeListChatModel(responses=["unused"])
    target = ProspectLiveTarget(
        orchestrator_model=model,
        specialist_model=model,
        prompt_revision="outreach-v4",
        interpreter_enabled=False,
    )
    example = langsmith_examples()[0]
    assert example.inputs is not None
    outputs = await target.ainvoke(example.inputs)

    assert build_options[0]["prompt_revision"] == "outreach-v4"
    assert build_options[0]["interpreter_enabled"] is False
    expected_hash = hashlib.sha256(b"cam-40:core_01").hexdigest()
    assert contexts[0].rep_id == expected_hash
    assert contexts[0].account_name == "Synthetic Core Shipper One"
    assert contexts[0].contact_name == "Jordan Lee"
    assert contexts[0].contact_role == "Logistics Manager"
    assert contexts[0].rep_display_name == "Alex Morgan"
    assert outputs["run_metadata"] == {"rep_id_hash": expected_hash}
    assert trace_metadata == [{"rep_id_hash": expected_hash}]
    assert run_metadata == [{"rep_id_hash": expected_hash}]
    assert outputs["pending_review"] is True
    observations = cast("Mapping[str, object]", outputs["artifact_observations"])
    contract = cast("Mapping[str, object]", observations["file_contract"])
    assert contract["unexpected"] == []
    assert outputs["tool_calls"] == ["task", "send_outreach"]
    assert outputs["trajectory_events"] == ["account_context.completed", "review.requested"]
    assert example.inputs["account_id"] not in repr(outputs)
    assert "input_payload" not in repr(outputs)


@pytest.mark.asyncio
async def test_live_target_rejects_incomplete_inputs() -> None:
    model = FakeListChatModel(responses=["unused"])
    target = ProspectLiveTarget(orchestrator_model=model, specialist_model=model)
    with pytest.raises(ValueError, match="incomplete"):
        await target.ainvoke({"example_id": "core_01"})


def test_live_target_rejects_archived_prompt_revisions() -> None:
    model = FakeListChatModel(responses=["unused"])

    with pytest.raises(ValueError, match="outreach-v4"):
        ProspectLiveTarget(
            orchestrator_model=model,
            specialist_model=model,
            prompt_revision="v1",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["account_name", "input_payload", "extra"])
async def test_live_target_rejects_hosted_input_drift(mutation: str) -> None:
    model = FakeListChatModel(responses=["unused"])
    target = ProspectLiveTarget(orchestrator_model=model, specialist_model=model)
    example = langsmith_examples()[0]
    assert example.inputs is not None
    inputs = deepcopy(dict(example.inputs))
    if mutation == "account_name":
        inputs["account_name"] = "Customer data"
    elif mutation == "input_payload":
        cast("dict[str, object]", inputs["input_payload"])["shipments_per_week"] = 99
    else:
        inputs["unreviewed"] = "content"

    with pytest.raises(ValueError, match="canonical synthetic dataset"):
        await target.ainvoke(inputs)
