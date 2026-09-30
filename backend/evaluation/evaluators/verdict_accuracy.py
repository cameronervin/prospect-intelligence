"""LangSmith evaluator for the lane-fit verdict."""

from collections.abc import Mapping

from langsmith.evaluation import EvaluationResult

from app.features.agent_quality.domain.lane_scoring import score_verdict_accuracy
from evaluation.contracts.snapshot import snapshot_artifacts


def evaluate_verdict_accuracy(
    outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
) -> EvaluationResult:
    expected_value = reference_outputs.get("expected_verdict")
    expected = expected_value if isinstance(expected_value, str) else ""
    signal = score_verdict_accuracy(snapshot_artifacts(outputs), expected)
    return EvaluationResult(
        key=signal.key,
        score=signal.score,
        metadata={"passed": signal.passed, **signal.metadata},
    )
