"""LangSmith evaluator for reference-aware top-lane precision."""

from collections.abc import Mapping

from langsmith.evaluation import EvaluationResult

from app.features.agent_quality.domain.lane_scoring import score_lane_precision
from evaluation.contracts.snapshot import snapshot_artifacts, snapshot_strings


def evaluate_lane_precision(
    outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
) -> EvaluationResult:
    signal = score_lane_precision(
        snapshot_artifacts(outputs),
        snapshot_strings(reference_outputs.get("expected_top_lanes")),
    )
    return EvaluationResult(
        key=signal.key,
        score=signal.score,
        metadata={"passed": signal.passed, **signal.metadata},
    )
