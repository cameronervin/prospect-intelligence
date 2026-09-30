"""LangSmith evaluator for informational run latency."""

from collections.abc import Mapping

from langsmith.evaluation import EvaluationResult

from app.features.agent_quality.domain.runtime_scoring import score_informational


def evaluate_latency(
    outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
) -> EvaluationResult:
    del reference_outputs
    signal = score_informational("latency_seconds", outputs.get("latency_seconds"))
    return EvaluationResult(key=signal.key, score=signal.score, metadata=dict(signal.metadata))
