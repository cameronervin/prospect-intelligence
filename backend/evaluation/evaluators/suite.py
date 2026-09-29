"""Single composition and release-policy boundary for offline evaluators."""

from collections.abc import Callable, Mapping

from langsmith.evaluation import EvaluationResult

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

EVALUATOR_VERSION = "freight-evaluators-v2"
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
OFFLINE_EVALUATORS: tuple[OfflineEvaluator, ...] = (
    evaluate_numeric_grounding,
    evaluate_lane_precision,
    evaluate_analysis_correctness,
    evaluate_verdict_accuracy,
    evaluate_file_contract,
    evaluate_trajectory,
    evaluate_injection_resistance,
    evaluate_latency,
    evaluate_cost,
    evaluate_tool_call_count,
)
