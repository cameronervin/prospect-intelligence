"""Human labels fail closed before they can become reference evidence."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from evaluation.experiments.alignment.contracts import (
    AdjudicationRecord,
    CalibrationCase,
    CalibrationLabel,
)
from evaluation.experiments.alignment.reference.cases import generate_calibration_cases
from evaluation.experiments.alignment.reference.labels import validate_calibration_labels
from evaluation.rubrics import QUESTIONS

NOW = datetime(2026, 10, 1, tzinfo=UTC)


def _value(case: CalibrationCase) -> bool | str | int:
    question = QUESTIONS[case.question_key]
    if question.kind == "noul":
        return "positive" in case.strata
    if question.kind == "choice":
        return next(tag.removeprefix("class:") for tag in case.strata if tag.startswith("class:"))
    return int(next(tag.removeprefix("score:") for tag in case.strata if tag.startswith("score:")))


def _label(case: CalibrationCase) -> CalibrationLabel:
    value = _value(case)
    ambiguous = "ambiguous" in case.strata
    confidence = "low" if ambiguous else "high"
    adjudication = (
        AdjudicationRecord(
            value=value,
            rationale="The second blind pass resolves the deliberately ambiguous fixture.",
            reviewer="Cameron Ervin",
            adjudicated_at=NOW + timedelta(minutes=1),
        )
        if ambiguous
        else None
    )
    return CalibrationLabel(
        case_id=case.case_id,
        question_key=case.question_key,
        state_hash=case.state_hash,
        value=value,
        confidence=confidence,
        rationale="The projected state satisfies the canonical semantic-v1 criterion.",
        ambiguous=ambiguous,
        reviewer="Cameron Ervin",
        labeled_at=NOW,
        label_set_version="cam-41-labels-v1",
        adjudication=adjudication,
    )


def test_complete_two_pass_label_set_is_accepted_in_case_order() -> None:
    cases = generate_calibration_cases()
    labels = tuple(reversed([_label(case) for case in cases]))

    approved = validate_calibration_labels(cases, labels)

    assert tuple(label.case_id for label in approved) == tuple(case.case_id for case in cases)


@pytest.mark.parametrize(
    ("question_key", "bad_value"),
    [
        ("internal_data_leak", "false"),
        ("next_step", "invent_a_lane"),
        ("actionability", 6),
        ("tone_fit", "3"),
    ],
)
def test_canonical_value_is_validated_by_question_kind(
    question_key: str, bad_value: object
) -> None:
    cases = generate_calibration_cases()
    case = next(item for item in cases if item.question_key == question_key)
    labels = [_label(item) for item in cases]
    index = cases.index(case)
    labels[index] = replace(labels[index], value=bad_value)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="canonical label"):
        validate_calibration_labels(cases, labels)


def test_ambiguous_or_low_confidence_labels_require_later_adjudication() -> None:
    cases = generate_calibration_cases()
    labels = [_label(case) for case in cases]
    index = next(index for index, label in enumerate(labels) if label.adjudication is not None)

    without_second_pass = replace(labels[index], adjudication=None)
    labels[index] = without_second_pass
    with pytest.raises(ValueError, match="second-pass adjudication"):
        validate_calibration_labels(cases, labels)

    labels[index] = replace(
        without_second_pass,
        adjudication=AdjudicationRecord(
            value=not bool(without_second_pass.value),
            rationale="The second blind pass changes the primary answer and becomes final.",
            reviewer="Cameron Ervin",
            adjudicated_at=NOW + timedelta(minutes=1),
        ),
    )
    approved = validate_calibration_labels(cases, labels)
    adjudication = approved[index].adjudication
    assert adjudication is not None
    assert adjudication.value != approved[index].value


def test_label_approval_rejects_missing_duplicate_and_drifted_records() -> None:
    cases = generate_calibration_cases()
    labels = [_label(case) for case in cases]

    with pytest.raises(ValueError, match="coverage"):
        validate_calibration_labels(cases, labels[1:])
    with pytest.raises(ValueError, match="duplicate label"):
        validate_calibration_labels(cases, (*labels, labels[0]))
    with pytest.raises(ValueError, match="label-set version"):
        validate_calibration_labels(
            cases, (replace(labels[0], label_set_version="v2"), *labels[1:])
        )
    with pytest.raises(ValueError, match="state hash"):
        validate_calibration_labels(cases, (replace(labels[0], state_hash="0" * 64), *labels[1:]))
