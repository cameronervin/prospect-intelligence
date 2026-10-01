"""Approval rules for blind, two-pass human preference labels."""

from __future__ import annotations

from collections.abc import Sequence

from evaluation.experiments.alignment.contracts import (
    CalibrationCase,
    CalibrationLabel,
    CanonicalLabel,
)
from evaluation.experiments.alignment.reference.cases import validate_calibration_cases
from evaluation.rubrics import QUESTIONS

LABEL_SET_VERSION = "cam-41-labels-v1"


def validate_canonical_label(question_key: str, value: object) -> CanonicalLabel:
    """Normalize no values: labels must already use the semantic-v1 canonical type and value."""

    question = QUESTIONS.get(question_key)
    if question is None:
        raise ValueError(f"unknown semantic question: {question_key}")
    if question.kind == "noul":
        if type(value) is not bool:
            raise ValueError(f"{question_key} canonical label must be boolean")
    elif question.kind == "choice":
        if not isinstance(value, str) or value not in question.options:
            raise ValueError(f"{question_key} canonical label must be one of its rubric options")
    elif type(value) is not int or str(value) not in question.options:
        raise ValueError(f"{question_key} canonical label must be an integer score from 1 to 5")
    return value


def requires_adjudication(label: CalibrationLabel) -> bool:
    """Low-confidence and explicitly ambiguous primary labels require a second blind pass."""

    return label.ambiguous or label.confidence == "low"


def validate_calibration_labels(
    cases: Sequence[CalibrationCase],
    labels: Sequence[CalibrationLabel],
    *,
    expected_label_set: str = LABEL_SET_VERSION,
) -> tuple[CalibrationLabel, ...]:
    """Return labels in case order only after full coverage and adjudication approval."""

    validate_calibration_cases(cases)
    if not expected_label_set.strip():
        raise ValueError("expected label-set version must be non-empty")

    by_case_id: dict[str, CalibrationLabel] = {}
    for label in labels:
        if label.case_id in by_case_id:
            raise ValueError(f"duplicate label for calibration case: {label.case_id}")
        by_case_id[label.case_id] = label

    expected_ids = {case.case_id for case in cases}
    if set(by_case_id) != expected_ids:
        missing = sorted(expected_ids.difference(by_case_id))
        unexpected = sorted(set(by_case_id).difference(expected_ids))
        raise ValueError(
            "label coverage must exactly match calibration cases "
            f"(missing={len(missing)}, unexpected={len(unexpected)})"
        )

    approved: list[CalibrationLabel] = []
    for case in cases:
        label = by_case_id[case.case_id]
        if label.question_key != case.question_key:
            raise ValueError(f"label question mismatch for case {case.case_id}")
        if label.state_hash != case.state_hash:
            raise ValueError(f"label state hash mismatch for case {case.case_id}")
        if label.label_set_version != expected_label_set:
            raise ValueError(f"label-set version mismatch for case {case.case_id}")
        validate_canonical_label(case.question_key, label.value)

        adjudication = label.adjudication
        if requires_adjudication(label) and adjudication is None:
            raise ValueError(f"second-pass adjudication required for case {case.case_id}")
        if adjudication is not None:
            validate_canonical_label(case.question_key, adjudication.value)
            if adjudication.adjudicated_at <= label.labeled_at:
                raise ValueError(
                    f"adjudication must follow the primary label for case {case.case_id}"
                )
        approved.append(label)
    return tuple(approved)
