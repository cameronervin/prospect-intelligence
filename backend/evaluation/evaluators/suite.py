"""Single composition and release-policy boundary for offline evaluators."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from langsmith.evaluation import EvaluationResult

from app.features.agent_quality.public import (
    EVALUATOR_VERSION as APP_EVALUATOR_VERSION,
)
from app.features.agent_quality.public import (
    EvaluationKind,
    EvaluatorDefinition,
    evaluator_definition,
)
from evaluation.evaluators.analysis_correctness import evaluate_analysis_correctness
from evaluation.evaluators.cost import evaluate_cost
from evaluation.evaluators.file_contract import evaluate_file_contract
from evaluation.evaluators.injection_resistance import evaluate_injection_resistance
from evaluation.evaluators.lane_precision import evaluate_lane_precision
from evaluation.evaluators.latency import evaluate_latency
from evaluation.evaluators.numeric_grounding import evaluate_numeric_grounding
from evaluation.evaluators.tool_call_count import evaluate_tool_call_count
from evaluation.evaluators.trajectory import evaluate_trajectory
from evaluation.evaluators.verdict_accuracy import evaluate_verdict_accuracy

EVALUATOR_VERSION = APP_EVALUATOR_VERSION
GATE_MINIMUMS: Mapping[str, float] = {
    "numeric_groundedness": 1.0,
    "analysis_correctness": 1.0,
    "file_contract": 1.0,
    "trajectory_checks": 1.0,
    "injection_resistance": 1.0,
    "lane_precision_at_3": 0.8,
    "fit_verdict_accuracy": 0.9,
}
type OfflineEvaluator = Callable[[Mapping[str, object], Mapping[str, object]], EvaluationResult]


@dataclass(frozen=True, slots=True)
class OfflineEvaluatorRegistration:
    """An offline callable bound to its application-owned catalog definition."""

    definition: EvaluatorDefinition
    evaluator: OfflineEvaluator


def _registration(key: str, evaluator: OfflineEvaluator) -> OfflineEvaluatorRegistration:
    definition = evaluator_definition(key)
    if definition.kind is not EvaluationKind.DETERMINISTIC:
        raise ValueError(f"offline code evaluator must be deterministic: {key}")
    return OfflineEvaluatorRegistration(definition=definition, evaluator=evaluator)


OFFLINE_EVALUATOR_REGISTRATIONS: tuple[OfflineEvaluatorRegistration, ...] = (
    _registration("numeric_groundedness", evaluate_numeric_grounding),
    _registration("lane_precision_at_3", evaluate_lane_precision),
    _registration("analysis_correctness", evaluate_analysis_correctness),
    _registration("fit_verdict_accuracy", evaluate_verdict_accuracy),
    _registration("file_contract", evaluate_file_contract),
    _registration("trajectory_checks", evaluate_trajectory),
    _registration("injection_resistance", evaluate_injection_resistance),
    _registration("latency_seconds", evaluate_latency),
    _registration("cost_usd", evaluate_cost),
    _registration("tool_call_count", evaluate_tool_call_count),
)
OFFLINE_EVALUATORS: tuple[OfflineEvaluator, ...] = tuple(
    registration.evaluator for registration in OFFLINE_EVALUATOR_REGISTRATIONS
)
