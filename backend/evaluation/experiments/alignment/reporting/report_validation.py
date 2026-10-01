"""Fail-closed validation for aggregate-only alignment reports."""

from __future__ import annotations

import math
from collections.abc import Mapping

from evaluation.experiments.alignment.calibration.models import QuestionJudgeSummary
from evaluation.rubrics import QUESTIONS


def safe_text(value: str, *, name: str) -> str:
    normalized = value.strip()
    if (
        not normalized
        or "`" in normalized
        or "\n" in normalized
        or "\r" in normalized
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
    ):
        raise ValueError(f"{name} must be safe single-line text")
    return normalized


def _allowed_labels(question_key: str) -> set[str]:
    question = QUESTIONS[question_key]
    if question.kind == "noul":
        return {"false", "true"}
    return set(question.options)


def _validate_confusion(question_key: str, confusion: Mapping[str, Mapping[str, int]]) -> None:
    allowed = _allowed_labels(question_key)
    for actual, predicted in confusion.items():
        if actual not in allowed or not set(predicted).issubset(allowed):
            raise ValueError("alignment report confusion contains a non-canonical label")
        if any(type(count) is not int or count < 0 for count in predicted.values()):
            raise ValueError("alignment report confusion contains an invalid count")


def validate_summary(summary: QuestionJudgeSummary) -> None:
    if summary.question_key not in QUESTIONS:
        raise ValueError("alignment report contains an unknown question")
    if summary.split not in {"alignment", "holdout"}:
        raise ValueError("alignment report contains an unknown split")
    if summary.judge_key not in {"jev", "sol"}:
        raise ValueError("alignment report contains an unknown judge")
    if summary.expected_attempts <= 0:
        raise ValueError("alignment report expected attempts must be positive")
    if summary.valid_attempts + summary.unavailable_attempts != summary.expected_attempts:
        raise ValueError("alignment report attempt coverage is inconsistent")
    if summary.costed_attempts + summary.cost_unavailable_attempts != summary.expected_attempts:
        raise ValueError("alignment report cost coverage is inconsistent")
    nonnegative = (
        summary.mean_absolute_error,
        summary.total_cost_usd,
        summary.reported_cost_usd,
        summary.total_latency_seconds,
    )
    if any(value is not None and (not math.isfinite(value) or value < 0) for value in nonnegative):
        raise ValueError("alignment report contains an invalid nonnegative metric")
    bounded = (
        summary.coverage,
        summary.cost_coverage,
    )
    if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in bounded):
        raise ValueError("alignment report contains an invalid bounded metric")
    optional_bounded = (
        summary.exact_agreement,
        summary.balanced_accuracy,
        summary.within_one_agreement,
        summary.run_to_run_disagreement,
        summary.order_sensitivity,
        summary.alternate_order_coverage,
    )
    if any(
        value is not None and (not math.isfinite(value) or not 0.0 <= value <= 1.0)
        for value in optional_bounded
    ):
        raise ValueError("alignment report contains an invalid optional metric")
    _validate_confusion(summary.question_key, summary.confusion)


__all__ = ["safe_text", "validate_summary"]
