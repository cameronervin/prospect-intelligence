"""Typed attempt and aggregate records for evaluator alignment."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from evaluation.contracts.judges import DecisionValue
from evaluation.experiments.alignment.contracts import AlignmentSplit

ATTEMPTS_PER_CASE = 3
AttemptStatus = Literal["valid", "unavailable"]


@dataclass(frozen=True, slots=True)
class CalibrationAttempt:
    """One independent judge observation; errors retain no provider payload."""

    case_id: str
    state_hash: str
    question_key: str
    split: AlignmentSplit
    judge_key: str
    attempt_index: int
    option_order: tuple[str, ...]
    human_label: bool | str | int | float
    predicted_value: DecisionValue | None
    status: AttemptStatus
    latency_seconds: float
    estimated_cost_usd: float | None
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class QuestionJudgeSummary:
    question_key: str
    split: AlignmentSplit
    judge_key: str
    expected_attempts: int
    valid_attempts: int
    unavailable_attempts: int
    coverage: float
    exact_agreement: float | None
    confusion: Mapping[str, Mapping[str, int]]
    balanced_accuracy: float | None
    class_imbalance: bool
    mean_absolute_error: float | None
    within_one_agreement: float | None
    per_case_disagreement: Mapping[str, float]
    run_to_run_disagreement: float | None
    order_sensitivity: float | None
    order_sensitive_cases: int
    order_sensitive_eligible_cases: int
    alternate_order_observations: int
    alternate_order_expected: int
    alternate_order_coverage: float | None
    total_cost_usd: float | None
    reported_cost_usd: float
    costed_attempts: int
    cost_unavailable_attempts: int
    cost_coverage: float
    total_latency_seconds: float


__all__ = [
    "ATTEMPTS_PER_CASE",
    "AlignmentSplit",
    "AttemptStatus",
    "CalibrationAttempt",
    "QuestionJudgeSummary",
]
