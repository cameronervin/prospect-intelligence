"""LangSmith evaluator for prompt-injection leakage and unsafe mutations."""

from collections.abc import Mapping

from langsmith.evaluation import EvaluationResult

from app.features.agent_quality.domain.runtime_scoring import score_injection_resistance
from evaluation.contracts.snapshot import snapshot_artifacts, snapshot_strings


def evaluate_injection_resistance(
    outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
) -> EvaluationResult:
    canary_value = reference_outputs.get("injection_canary")
    canary = canary_value if isinstance(canary_value, str) else None
    artifacts = snapshot_artifacts(outputs)
    signal = score_injection_resistance(
        artifacts,
        snapshot_strings(outputs.get("tool_calls")),
        canary=canary,
        snapshot_present=bool(artifacts) and isinstance(outputs.get("tool_calls"), list),
    )
    return EvaluationResult(
        key=signal.key,
        score=signal.score,
        metadata={"passed": signal.passed, **signal.metadata},
    )
