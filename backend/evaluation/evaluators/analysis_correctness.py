"""LangSmith evaluator for complete ranked lane-analysis correctness."""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import cast

from langsmith.evaluation import EvaluationResult

from app.features.prospect_intelligence.public import PROSPECT_FILES, LaneAnalysisArtifact
from evaluation.contracts.observations import decimal_value, json_object
from evaluation.contracts.snapshot import snapshot_artifacts, snapshot_mapping
from evaluation.references.lane_fit_v1 import ReferenceLaneScore, evaluate_lane_fit

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


def _predicted(artifacts: Mapping[str, str]) -> tuple[str, Sequence[object]]:
    parsed = LaneAnalysisArtifact.from_json(artifacts.get(PROSPECT_FILES.lane_fit_json, ""))
    lanes = json_object(artifacts, PROSPECT_FILES.lane_fit_json)["top_lanes"]
    if not isinstance(lanes, Sequence) or isinstance(lanes, (str, bytes, bytearray)):
        raise ValueError("analysis top_lanes must be an array")
    return parsed.verdict.value, cast("Sequence[object]", lanes)


def _expected(lane: ReferenceLaneScore) -> Mapping[str, object]:
    return {
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


def _failure(error: str) -> EvaluationResult:
    return EvaluationResult(
        key="analysis_correctness",
        score=0.0,
        metadata={"passed": False, "error": error, "missing": [], "extra": [], "mismatched": []},
    )


def evaluate_analysis_correctness(
    outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
) -> EvaluationResult:
    artifacts = snapshot_artifacts(outputs)
    input_payload = snapshot_mapping(reference_outputs.get("input_payload"))
    try:
        expected = evaluate_lane_fit(input_payload)
        predicted_verdict, raw_lanes = _predicted(artifacts)
    except (KeyError, TypeError, ValueError) as error:
        return _failure(str(error))
    expected_lanes = tuple(_expected(lane) for lane in expected.lanes)
    missing = list(range(len(raw_lanes), len(expected_lanes)))
    extra = list(range(len(expected_lanes), len(raw_lanes)))
    mismatched: list[dict[str, object]] = []
    matching_fields = int(predicted_verdict == expected.verdict)
    if not matching_fields:
        mismatched.append(
            {"field": "verdict", "predicted": predicted_verdict, "expected": expected.verdict}
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
                    matches = abs(decimal_value(actual) - cast(Decimal, wanted)) <= tolerance
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
    return EvaluationResult(
        key="analysis_correctness",
        score=matching_fields / max(total_fields, 1),
        metadata={
            "passed": passed,
            "missing": missing,
            "extra": extra,
            "mismatched": mismatched,
            "tolerance": 1e-6,
            "expected_verdict": expected.verdict,
        },
    )
