"""Offline LangSmith wrappers preserve the application-owned scoring semantics."""

from collections.abc import Callable, Mapping
from typing import Any, cast

import pytest
from langsmith.evaluation import EvaluationResult

from app.features.agent_quality.contracts.models import QualitySignal
from app.features.agent_quality.domain.deterministic import (
    score_numeric_grounding,
    trajectory_signal,
)
from app.features.agent_quality.domain.lane_scoring import (
    score_analysis_correctness,
    score_lane_precision,
    score_verdict_accuracy,
)
from app.features.agent_quality.domain.runtime_scoring import (
    score_file_contract,
    score_informational,
    score_injection_resistance,
)
from app.features.prospect_intelligence.public import PROSPECT_FILES
from evaluation.contracts.observations import decimal_value
from evaluation.contracts.snapshot import snapshot_mapping, snapshot_observations
from evaluation.datasets import generate_dataset
from evaluation.evaluators.analysis_correctness import evaluate_analysis_correctness
from evaluation.evaluators.cost import evaluate_cost
from evaluation.evaluators.file_contract import evaluate_file_contract
from evaluation.evaluators.injection_resistance import evaluate_injection_resistance
from evaluation.evaluators.lane_precision import evaluate_lane_precision
from evaluation.evaluators.latency import evaluate_latency
from evaluation.evaluators.numeric_grounding import evaluate_numeric_grounding
from evaluation.evaluators.tool_call_count import evaluate_tool_call_count
from evaluation.evaluators.trajectory import evaluate_trajectory
from evaluation.evaluators.verdict_accuracy import evaluate_verdict_accuracy
from evaluation.references.lane_fit_v1 import evaluate_lane_fit
from tests.unit.evaluation.support import artifacts, outputs


def _metadata(result: EvaluationResult) -> Mapping[str, object]:
    return cast("Mapping[str, object]", cast(Any, result).metadata or {})


def _assert_parity(result: EvaluationResult, signal: QualitySignal) -> None:
    assert result.key == signal.key
    assert result.score == signal.score
    metadata = _metadata(result)
    if signal.passed is not None:
        assert metadata["passed"] is signal.passed
    assert all(metadata[key] == value for key, value in signal.metadata.items())


def _numeric_signal(snapshot: Mapping[str, object]) -> QualitySignal:
    observation = snapshot_mapping(snapshot_observations(snapshot).get("numeric_evidence"))
    raw_values = cast("list[str]", observation["values"])
    return score_numeric_grounding(
        cast("Mapping[str, str]", snapshot["artifacts"]),
        {decimal_value(value) for value in raw_values},
        cast("list[str]", observation["invalid_evidence"]),
    )


def _expected_lane_payloads() -> tuple[str, tuple[Mapping[str, object], ...]]:
    expected = evaluate_lane_fit(generate_dataset()[0].input_payload)
    lanes = tuple(
        {
            "origin": lane.origin,
            "destination": lane.destination,
            "shipper_loads_per_week": lane.shipper_loads_per_week,
            "matched_loads_per_week": lane.matched_loads_per_week,
            "backhaul_fill": lane.backhaul_fill,
            "density": lane.density,
            "equipment_match": lane.equipment_match,
            "fit_score": lane.fit_score,
            "modeled_annual_revenue": lane.modeled_annual_revenue,
            "deadhead_miles_avoided": lane.deadhead_miles_avoided,
            "method_version": "lane_fit_v1",
        }
        for lane in expected.lanes
    )
    return expected.verdict, lanes


def test_artifact_and_safety_wrappers_match_shared_core_on_success_and_failure() -> None:
    safe_snapshot = outputs(artifacts())
    unsafe_values = artifacts()
    unsafe_values[PROSPECT_FILES.outreach_draft] += " PLANTED-CANARY"
    unsafe_snapshot = outputs(unsafe_values)
    unsafe_snapshot["tool_calls"] = ["update_crm"]

    for snapshot in (safe_snapshot, {}):
        observation = snapshot_mapping(snapshot_observations(snapshot).get("file_contract"))
        _assert_parity(evaluate_file_contract(snapshot, {}), score_file_contract(observation))
    for snapshot in (safe_snapshot, unsafe_snapshot):
        artifacts_value = cast("Mapping[str, str]", snapshot["artifacts"])
        tools = cast("list[str]", snapshot["tool_calls"])
        expected = score_injection_resistance(
            artifacts_value,
            tools,
            canary="planted-canary",
            snapshot_present=True,
        )
        _assert_parity(
            evaluate_injection_resistance(snapshot, {"injection_canary": "planted-canary"}),
            expected,
        )


def test_reference_wrappers_match_shared_core_on_success_and_failure() -> None:
    values = artifacts()
    snapshot = outputs(values)
    verdict, expected_lanes = _expected_lane_payloads()
    expected_names = tuple(f"{lane['origin']}-{lane['destination']}" for lane in expected_lanes)
    reference = {
        "expected_top_lanes": expected_names,
        "expected_verdict": verdict,
        "input_payload": generate_dataset()[0].input_payload,
    }

    for candidate in (snapshot, {}):
        candidate_artifacts = cast("Mapping[str, str]", candidate.get("artifacts", {}))
        _assert_parity(
            evaluate_lane_precision(candidate, reference),
            score_lane_precision(candidate_artifacts, expected_names),
        )
        _assert_parity(
            evaluate_verdict_accuracy(candidate, reference),
            score_verdict_accuracy(candidate_artifacts, verdict),
        )
        _assert_parity(
            evaluate_analysis_correctness(candidate, reference),
            score_analysis_correctness(candidate_artifacts, verdict, expected_lanes),
        )


def test_numeric_and_trajectory_wrappers_match_shared_core_on_success_and_failure() -> None:
    grounded = outputs(artifacts())
    unsupported_values = artifacts()
    unsupported_values[PROSPECT_FILES.sales_brief] += " Unsupported 2026."
    unsupported = outputs(unsupported_values)
    for snapshot in (grounded, unsupported):
        _assert_parity(evaluate_numeric_grounding(snapshot, {}), _numeric_signal(snapshot))

    good_events = [
        "account_context.completed",
        "external_research.completed",
        "lane_analyst.completed",
        "outreach_drafter.completed",
        "quality_review.completed",
        "review.requested",
    ]
    for events, pending in ((good_events, True), (["lane_analyst.completed"], False)):
        snapshot = {"trajectory_events": events, "pending_review": pending}
        signal = trajectory_signal(events, pending_review=pending, latency_seconds=0.0)
        result = evaluate_trajectory(snapshot, {})
        assert result.score == signal.score
        assert _metadata(result)["violations"] == signal.metadata["violations"]


@pytest.mark.parametrize(
    ("key", "evaluator", "value"),
    [
        ("latency_seconds", evaluate_latency, 1.25),
        ("cost_usd", evaluate_cost, 0.02),
        ("tool_call_count", evaluate_tool_call_count, 9),
    ],
)
def test_informational_wrappers_match_shared_core_when_present_or_missing(
    key: str,
    evaluator: Callable[[Mapping[str, object], Mapping[str, object]], EvaluationResult],
    value: object,
) -> None:
    for snapshot in ({key: value}, {}):
        _assert_parity(evaluator(snapshot, {}), score_informational(key, snapshot.get(key)))
