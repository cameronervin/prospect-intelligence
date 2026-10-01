"""Hosted target failures remain sanitized, measured experiment rows."""

import hashlib
from collections.abc import Mapping
from typing import cast

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.features.prospect_intelligence.contracts.agent_runtime import ProspectAgentResult
from evaluation.datasets import langsmith_examples
from evaluation.targets import prospect_live as live_target
from evaluation.targets.prospect_live import ProspectLiveTarget


@pytest.mark.asyncio
async def test_live_target_preserves_sanitized_cost_and_latency_on_runtime_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingRuntime:
        async def execute(self, *_: object, **__: object) -> ProspectAgentResult:
            raise RuntimeError("private provider detail")

    def build_failing_runtime(**_kwargs: object) -> FailingRuntime:
        return FailingRuntime()

    monkeypatch.setattr(
        live_target,
        "build_prospect_agent_runtime",
        build_failing_runtime,
    )
    model = FakeListChatModel(responses=["unused"])
    target = ProspectLiveTarget(orchestrator_model=model, specialist_model=model)
    example = langsmith_examples()[0]
    assert example.inputs is not None

    outputs = await target.ainvoke(example.inputs)

    assert outputs["artifacts"] == {}
    assert outputs["cost_usd"] == 0.0
    assert isinstance(outputs["latency_seconds"], float)
    metadata = cast("Mapping[str, object]", outputs["run_metadata"])
    assert metadata["status"] == "target_error"
    assert metadata["error_type"] == "RuntimeError"
    assert "private provider detail" not in repr(outputs)


@pytest.mark.asyncio
async def test_live_target_sanitizes_postprocessing_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MalformedRuntime:
        async def execute(self, *_: object, **__: object) -> ProspectAgentResult:
            return ProspectAgentResult(
                files={},
                completed_stages=(),
                pending_interrupt=None,
                raw={"messages": []},
            )

    def build_malformed_runtime(**_kwargs: object) -> MalformedRuntime:
        return MalformedRuntime()

    monkeypatch.setattr(
        live_target,
        "build_prospect_agent_runtime",
        build_malformed_runtime,
    )
    model = FakeListChatModel(responses=["unused"])
    target = ProspectLiveTarget(orchestrator_model=model, specialist_model=model)
    example = langsmith_examples()[0]
    assert example.inputs is not None

    outputs = await target.ainvoke(example.inputs)

    assert outputs["artifacts"] == {}
    assert isinstance(outputs["latency_seconds"], float)
    metadata = cast("Mapping[str, object]", outputs["run_metadata"])
    assert metadata == {
        "rep_id_hash": hashlib.sha256(b"cam-40:core_01").hexdigest(),
        "status": "target_error",
        "error_type": "KeyError",
    }
