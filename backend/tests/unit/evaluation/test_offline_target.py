"""Compiled-graph target and sanitized snapshot behavior."""

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from typing import Any, cast

import pytest

from app.features.prospect_intelligence.public import PROSPECT_FILES
from evaluation.contracts.snapshot import decode_artifacts, normalize_snapshot
from evaluation.datasets import langsmith_examples
from evaluation.evaluators.file_contract import evaluate_file_contract
from evaluation.targets import prospect_graph
from evaluation.targets.prospect_graph import ProspectOfflineTarget
from tests.unit.prospect_intelligence.agent_test_support import completed_files, file_data


def test_decode_artifacts_accepts_only_utf8_file_data() -> None:
    assert decode_artifacts({"/output/brief.md": {"content": "safe", "encoding": "utf-8"}}) == {
        "/output/brief.md": "safe"
    }
    with pytest.raises(ValueError, match="utf-8"):
        decode_artifacts({"/output/brief.md": {"content": "unsafe", "encoding": "base64"}})


def test_snapshot_observes_unexpected_runtime_file_without_exposing_its_body() -> None:
    files = completed_files()
    files["/output/secret.txt"] = file_data("PRIVATE-SOURCE-BODY")
    snapshot = normalize_snapshot(
        files=cast("Mapping[str, object]", files),
        analysis={"verdict": "fit"},
        trajectory_events=(),
        tool_calls=(),
        pending_review=True,
        latency_seconds=0.1,
    ).to_outputs()
    assert "PRIVATE-SOURCE-BODY" not in repr(snapshot)
    observations = cast("Mapping[str, object]", snapshot["artifact_observations"])
    contract = cast("Mapping[str, object]", observations["file_contract"])
    assert contract["unexpected"] == ["/output/secret.txt"]
    assert contract["actual_count"] == 12
    result = evaluate_file_contract(snapshot, {})
    assert isinstance(result.score, (int, float)) and result.score < 1.0
    metadata = cast(
        "Mapping[str, object] | None",
        result.metadata,  # pyright: ignore[reportUnknownMemberType]
    )
    assert metadata is not None and metadata["passed"] is False


@pytest.mark.asyncio
async def test_target_runs_one_scenario_through_compiled_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracing_modes: list[object] = []
    original_context = cast(
        Any,
        prospect_graph.tracing_context,  # pyright: ignore[reportUnknownMemberType]
    )

    @contextmanager
    def recording_context(**kwargs: object):
        tracing_modes.append(kwargs.get("enabled"))
        with original_context(**cast(Any, kwargs)):
            yield

    monkeypatch.setattr(prospect_graph, "tracing_context", recording_context)
    example = langsmith_examples()[0]
    assert example.inputs is not None
    snapshot = await ProspectOfflineTarget().ainvoke(example.inputs)
    artifacts = cast("Mapping[str, str]", snapshot["artifacts"])
    assert set(artifacts) == {
        PROSPECT_FILES.lane_fit_json,
        PROSPECT_FILES.lane_fit_markdown,
        PROSPECT_FILES.sales_brief,
        PROSPECT_FILES.outreach_draft,
    }
    assert not any(path.startswith(("/task/", "/context/", "/research/")) for path in artifacts)
    assert cast(str, example.inputs["account_id"]) not in repr(snapshot)
    observations = cast("Mapping[str, object]", snapshot["artifact_observations"])
    assert observations["file_contract"] == {
        "actual_count": 11,
        "expected_count": 11,
        "invalid_json": [],
        "invalid_schema": [],
        "missing": [],
        "unexpected": [],
    }
    assert snapshot["pending_review"] is True
    assert snapshot["verdict"] == "fit"
    assert snapshot["trajectory_events"] == [
        "account_context.completed",
        "external_research.completed",
        "lane_analyst.completed",
        "outreach_drafter.completed",
        "review.requested",
    ]
    tool_calls = cast("Sequence[str]", snapshot["tool_calls"])
    assert tool_calls.count("task") == 4
    assert tool_calls.count("write_file") == 9
    assert "send_outreach" in tool_calls
    assert snapshot["tool_call_count"] == 17
    semantic = cast("Mapping[str, object]", snapshot["semantic_observations"])
    assert set(semantic) == {
        "claim_supported",
        "internal_data_leak",
        "draft_matches_brief",
        "next_step",
        "entity_resolution_ok",
        "actionability",
        "tone_fit",
    }
    assert cast("list[object]", semantic["claim_supported"])
    assert (
        cast("Mapping[str, object]", semantic["entity_resolution_ok"])["account_name"]
        == example.inputs["account_name"]
    )
    assert semantic["tone_fit"] is None
    assert "input_payload" not in repr(semantic)
    assert "messages" not in snapshot and "task_brief" not in snapshot
    assert tracing_modes == [False]


@pytest.mark.asyncio
async def test_target_preserves_unavailable_source_state_in_safe_observation() -> None:
    example = next(
        item
        for item in langsmith_examples()
        if item.inputs is not None and item.inputs["example_id"] == "edge_01"
    )
    assert example.inputs is not None
    snapshot = await ProspectOfflineTarget().ainvoke(example.inputs)
    assert snapshot["verdict"] == "needs_more_data"
    observations = cast("Mapping[str, object]", snapshot["artifact_observations"])
    source_states = cast("Mapping[str, object]", observations["source_states"])
    assert source_states[PROSPECT_FILES.freight_research] == {
        "coverage": "unavailable",
        "dependency_failed": False,
    }
