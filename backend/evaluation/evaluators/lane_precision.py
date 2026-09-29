"""LangSmith evaluator for reference-aware top-lane precision."""

import json
from collections.abc import Mapping, Sequence
from typing import cast

from langsmith.evaluation import EvaluationResult

from app.features.prospect_intelligence.public import PROSPECT_FILES
from evaluation.contracts.snapshot import snapshot_artifacts, snapshot_strings


def _predicted_lanes(artifacts: Mapping[str, str]) -> tuple[str, ...]:
    try:
        raw = cast(object, json.loads(artifacts.get(PROSPECT_FILES.lane_fit_json, "")))
    except json.JSONDecodeError:
        return ()
    if not isinstance(raw, Mapping):
        return ()
    lanes = cast("Mapping[str, object]", raw).get("top_lanes")
    if not isinstance(lanes, Sequence) or isinstance(lanes, (str, bytes, bytearray)):
        return ()
    names: list[str] = []
    for item in cast("Sequence[object]", lanes):
        if isinstance(item, Mapping):
            lane = cast("Mapping[str, object]", item)
            origin, destination = lane.get("origin"), lane.get("destination")
            if isinstance(origin, str) and isinstance(destination, str):
                names.append(f"{origin}-{destination}")
    return tuple(names)


def _unique_top(values: Sequence[str], k: int = 3) -> tuple[str, ...]:
    selected: list[str] = []
    for value in values:
        if value not in selected:
            selected.append(value)
        if len(selected) == k:
            break
    return tuple(selected)


def evaluate_lane_precision(
    outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
) -> EvaluationResult:
    artifacts = snapshot_artifacts(outputs)
    predicted = _unique_top(_predicted_lanes(artifacts))
    expected = _unique_top(snapshot_strings(reference_outputs.get("expected_top_lanes")))
    denominator = max(len(predicted), len(expected))
    score = len(set(predicted).intersection(expected)) / denominator if denominator else 1.0
    if not artifacts:
        score = 0.0
    metric_name = "lane_precision_at_3"
    return EvaluationResult(
        key=metric_name,
        score=score,
        metadata={
            "passed": score >= 0.8,
            "predicted": predicted,
            "expected": expected,
        },
    )
