"""LangSmith evaluator for informational tool-call count."""

from collections.abc import Mapping

from langsmith.evaluation import EvaluationResult


def evaluate_tool_call_count(
    outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
) -> EvaluationResult:
    del reference_outputs
    value = outputs.get("tool_call_count")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return EvaluationResult(key="tool_call_count", score=None, metadata={"missing": True})
    return EvaluationResult(key="tool_call_count", score=value, metadata={"informational": True})
