"""Canonical labels and class-balanced metrics for alignment attempts."""

import math
from collections import defaultdict
from collections.abc import Sequence
from statistics import fmean

from evaluation.experiments.alignment.calibration.models import CalibrationAttempt
from evaluation.rubrics import QUESTIONS


def canonical_label_key(question_key: str, value: bool | str | int | float | None) -> str:
    if value is None:
        raise ValueError("a valid calibration value cannot be null")
    question = QUESTIONS[question_key]
    if question.kind == "score":
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("a valid score calibration value must be numeric")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("a valid score calibration value must be finite")
        canonical = math.floor(numeric + 0.5)
        if str(canonical) not in question.options:
            raise ValueError("a valid score calibration value is outside the rubric")
        return str(canonical)
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def human_agreement(
    question_key: str,
    predicted_value: bool | str | int | float,
    human_label: bool | str | int | float,
) -> bool:
    """Apply the reporting contract to persisted human-agreement feedback."""

    return canonical_label_key(question_key, predicted_value) == canonical_label_key(
        question_key, human_label
    )


def balanced_accuracy(
    question_key: str,
    valid: Sequence[CalibrationAttempt],
) -> tuple[float | None, bool]:
    question = QUESTIONS[question_key]
    required = (
        ("false", "true")
        if question.kind == "noul"
        else question.options
        if question.kind == "choice"
        else ()
    )
    if not required:
        return None, False
    by_label: dict[str, list[CalibrationAttempt]] = defaultdict(list)
    for attempt in valid:
        by_label[canonical_label_key(question_key, attempt.human_label)].append(attempt)
    if any(not by_label[label] for label in required):
        return None, True
    recalls = [
        sum(
            canonical_label_key(question_key, attempt.predicted_value) == label
            for attempt in by_label[label]
            if attempt.predicted_value is not None
        )
        / len(by_label[label])
        for label in required
    ]
    return fmean(recalls), False


__all__ = ["balanced_accuracy", "canonical_label_key", "human_agreement"]
