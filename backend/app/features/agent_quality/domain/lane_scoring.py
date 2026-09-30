"""SDK-neutral reference-aware lane-analysis scoring."""

import json
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import cast

from app.features.agent_quality.contracts.models import QualitySignal
from app.features.prospect_intelligence.public import (
    PROSPECT_FILES,
    AnalysisOutput,
    LaneAnalysisArtifact,
)

_TEXT_FIELDS = ("origin", "destination", "method_version")
_INTEGER_FIELDS = ("shipper_loads_per_week", "matched_loads_per_week", "deadhead_miles_avoided")
_DECIMAL_FIELDS = (
    "backhaul_fill",
    "density",
    "equipment_match",
    "fit_score",
    "modeled_annual_revenue",
)
_LANE_FIELDS = (*_TEXT_FIELDS, *_INTEGER_FIELDS, *_DECIMAL_FIELDS)


def _lane_payload(lane: object) -> dict[str, object]:
    return {field: getattr(lane, field) for field in _LANE_FIELDS}


def expected_lane_analysis(output: AnalysisOutput) -> tuple[str, tuple[Mapping[str, object], ...]]:
    return output.verdict.value, tuple(_lane_payload(item.score) for item in output.brief.lanes)


def _json_object(artifacts: Mapping[str, str]) -> Mapping[str, object]:
    try:
        raw = cast(object, json.loads(artifacts.get(PROSPECT_FILES.lane_fit_json, "")))
    except json.JSONDecodeError as error:
        raise ValueError("lane analysis must contain valid JSON") from error
    if not isinstance(raw, Mapping):
        raise ValueError("lane analysis must be a JSON object")
    return cast("Mapping[str, object]", raw)


def _raw_lanes(artifacts: Mapping[str, str]) -> tuple[str, Sequence[object]]:
    parsed = _json_object(artifacts)
    verdict = parsed.get("verdict")
    lanes = parsed.get("top_lanes")
    if not isinstance(verdict, str):
        raise ValueError("lane analysis verdict is invalid")
    if not isinstance(lanes, Sequence) or isinstance(lanes, (str, bytes, bytearray)):
        raise ValueError("analysis top_lanes must be an array")
    return verdict, cast("Sequence[object]", lanes)


def _lane_names(artifacts: Mapping[str, str]) -> tuple[str, ...]:
    try:
        lanes = _raw_lanes(artifacts)[1]
    except ValueError:
        return ()
    names: list[str] = []
    for item in lanes:
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


def score_lane_precision(
    artifacts: Mapping[str, str], expected_names: Sequence[str]
) -> QualitySignal:
    predicted = _unique_top(_lane_names(artifacts))
    expected = _unique_top(expected_names)
    denominator = max(len(predicted), len(expected))
    score = len(set(predicted).intersection(expected)) / denominator if denominator else 1.0
    if not artifacts:
        score = 0.0
    return QualitySignal(
        "lane_precision_at_3",
        score,
        score >= 0.8,
        metadata={"predicted": predicted, "expected": expected},
    )


def score_verdict_accuracy(artifacts: Mapping[str, str], expected: str) -> QualitySignal:
    try:
        value = _json_object(artifacts).get("verdict")
    except ValueError:
        value = None
    predicted = value if isinstance(value, str) else ""
    passed = bool(artifacts) and bool(expected) and predicted == expected
    return QualitySignal(
        "fit_verdict_accuracy",
        1.0 if passed else 0.0,
        passed,
        metadata={"predicted": predicted, "expected": expected},
    )


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("value must be numeric")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("value must be numeric") from error
    if not parsed.is_finite():
        raise ValueError("value must be finite")
    return parsed


def _analysis_failure(error: str) -> QualitySignal:
    return QualitySignal(
        "analysis_correctness",
        0.0,
        False,
        metadata={"error": error, "missing": [], "extra": [], "mismatched": []},
    )


def score_analysis_correctness(
    artifacts: Mapping[str, str],
    expected_verdict: str,
    expected_lanes: Sequence[Mapping[str, object]],
) -> QualitySignal:
    try:
        LaneAnalysisArtifact.from_json(artifacts.get(PROSPECT_FILES.lane_fit_json, ""))
        predicted_verdict, raw_lanes = _raw_lanes(artifacts)
    except ValueError as error:
        return _analysis_failure(str(error))
    missing = list(range(len(raw_lanes), len(expected_lanes)))
    extra = list(range(len(expected_lanes), len(raw_lanes)))
    mismatched: list[dict[str, object]] = []
    matching_fields = int(predicted_verdict == expected_verdict)
    if not matching_fields:
        mismatched.append(
            {"field": "verdict", "predicted": predicted_verdict, "expected": expected_verdict}
        )
    tolerance = Decimal("1e-6")
    for index, expected_lane in enumerate(expected_lanes):
        if index >= len(raw_lanes):
            continue
        raw_lane = raw_lanes[index]
        if not isinstance(raw_lane, Mapping):
            mismatched.append({"index": index, "field": "lane", "reason": "not an object"})
            continue
        predicted_lane = cast("Mapping[str, object]", raw_lane)
        for field in _LANE_FIELDS:
            actual, wanted = predicted_lane.get(field), expected_lane[field]
            try:
                if field in _DECIMAL_FIELDS:
                    matches = abs(_decimal(actual) - _decimal(wanted)) <= tolerance
                elif field in _INTEGER_FIELDS:
                    matches = (
                        not isinstance(actual, bool)
                        and isinstance(actual, int)
                        and actual == wanted
                    )
                else:
                    matches = actual == wanted
            except ValueError:
                matches = False
            if matches:
                matching_fields += 1
            else:
                mismatched.append(
                    {"index": index, "field": field, "predicted": actual, "expected": str(wanted)}
                )
    total_fields = 1 + max(len(expected_lanes), len(raw_lanes)) * len(_LANE_FIELDS)
    passed = not missing and not extra and not mismatched
    return QualitySignal(
        "analysis_correctness",
        matching_fields / max(total_fields, 1),
        passed,
        metadata={
            "missing": missing,
            "extra": extra,
            "mismatched": mismatched,
            "tolerance": 1e-6,
            "expected_verdict": expected_verdict,
        },
    )


def lane_reference_signals(
    artifacts: Mapping[str, str], expected: AnalysisOutput
) -> tuple[QualitySignal, QualitySignal, QualitySignal]:
    verdict, lanes = expected_lane_analysis(expected)
    names = tuple(f"{lane['origin']}-{lane['destination']}" for lane in lanes)
    return (
        score_lane_precision(artifacts, names),
        score_analysis_correctness(artifacts, verdict, lanes),
        score_verdict_accuracy(artifacts, verdict),
    )
