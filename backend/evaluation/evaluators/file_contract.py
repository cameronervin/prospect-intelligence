"""LangSmith evaluator for the runtime artifact contract."""

from collections.abc import Mapping

from langsmith.evaluation import EvaluationResult

from app.features.agent_quality.domain.runtime_scoring import score_file_contract
from evaluation.contracts.snapshot import snapshot_mapping, snapshot_observations


def evaluate_file_contract(
    outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
) -> EvaluationResult:
    del reference_outputs
    signal = score_file_contract(
        snapshot_mapping(snapshot_observations(outputs).get("file_contract"))
    )
    return EvaluationResult(
        key=signal.key,
        score=signal.score,
        metadata={"passed": signal.passed, **signal.metadata},
    )
