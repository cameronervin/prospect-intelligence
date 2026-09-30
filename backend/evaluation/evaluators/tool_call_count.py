"""LangSmith evaluator for informational tool-call count."""

from collections.abc import Mapping

from langsmith.evaluation import EvaluationResult

from app.features.agent_quality.domain.runtime_scoring import score_informational


def evaluate_tool_call_count(
    outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
) -> EvaluationResult:
    del reference_outputs
    signal = score_informational("tool_call_count", outputs.get("tool_call_count"))
    return EvaluationResult(key=signal.key, score=signal.score, metadata=dict(signal.metadata))
