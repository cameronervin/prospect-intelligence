"""LangSmith evaluator for informational run latency."""

from collections.abc import Mapping

from langsmith.evaluation import EvaluationResult


def evaluate_latency(
    outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
) -> EvaluationResult:
    del reference_outputs
    value = outputs.get("latency_seconds")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return EvaluationResult(key="latency_seconds", score=None, metadata={"missing": True})
    return EvaluationResult(key="latency_seconds", score=value, metadata={"informational": True})
