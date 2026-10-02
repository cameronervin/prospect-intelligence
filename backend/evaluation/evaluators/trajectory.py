"""LangSmith evaluator for delegated tool-call trajectory safety."""

from collections.abc import Mapping

from langsmith.evaluation import EvaluationResult

from app.features.agent_quality.domain.deterministic import trajectory_signal
from evaluation.contracts.snapshot import snapshot_strings


def evaluate_trajectory(
    outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
) -> EvaluationResult:
    del reference_outputs
    signal = trajectory_signal(
        snapshot_strings(outputs.get("trajectory_events")),
        pending_review=outputs.get("pending_review") is True,
        latency_seconds=0.0,
        review_required=outputs.get("verdict") not in {"no_fit", "needs_more_data"},
    )
    return EvaluationResult(
        key=signal.key,
        score=signal.score,
        metadata={
            "passed": signal.passed,
            "violations": signal.metadata["violations"],
        },
    )
