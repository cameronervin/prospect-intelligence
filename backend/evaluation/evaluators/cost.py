"""LangSmith evaluator for informational run cost."""

from collections.abc import Mapping

from langsmith.evaluation import EvaluationResult

from app.features.agent_quality.domain.runtime_scoring import score_informational


def evaluate_cost(
    outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
) -> EvaluationResult:
    del reference_outputs
    signal = score_informational("cost_usd", outputs.get("cost_usd"))
    return EvaluationResult(key=signal.key, score=signal.score, metadata=dict(signal.metadata))
