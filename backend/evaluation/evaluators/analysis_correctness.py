"""LangSmith evaluator for complete ranked lane-analysis correctness."""

from collections.abc import Mapping

from langsmith.evaluation import EvaluationResult

from app.features.agent_quality.domain.lane_scoring import score_analysis_correctness
from evaluation.contracts.snapshot import snapshot_artifacts, snapshot_mapping
from evaluation.references.lane_fit_v1 import ReferenceLaneScore, evaluate_lane_fit


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


def evaluate_analysis_correctness(
    outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
) -> EvaluationResult:
    artifacts = snapshot_artifacts(outputs)
    input_payload = snapshot_mapping(reference_outputs.get("input_payload"))
    try:
        expected = evaluate_lane_fit(input_payload)
    except (KeyError, TypeError, ValueError) as error:
        return EvaluationResult(
            key="analysis_correctness",
            score=0.0,
            metadata={
                "passed": False,
                "error": str(error),
                "missing": [],
                "extra": [],
                "mismatched": [],
            },
        )
    expected_lanes = tuple(_expected(lane) for lane in expected.lanes)
    signal = score_analysis_correctness(artifacts, expected.verdict, expected_lanes)
    return EvaluationResult(
        key=signal.key,
        score=signal.score,
        metadata={"passed": signal.passed, **signal.metadata},
    )
