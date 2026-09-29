"""LangSmith evaluator for informational run cost."""

from collections.abc import Mapping

from langsmith.evaluation import EvaluationResult


def evaluate_cost(
    outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
) -> EvaluationResult:
    del reference_outputs
    value = outputs.get("cost_usd")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return EvaluationResult(key="cost_usd", score=None, metadata={"missing": True})
    return EvaluationResult(key="cost_usd", score=value, metadata={"informational": True})
