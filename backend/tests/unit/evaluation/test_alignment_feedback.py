"""LangSmith feedback is converted into strict versioned human labels."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest

from evaluation.experiments.alignment.reference.cases import generate_calibration_cases
from evaluation.experiments.alignment.reference.feedback import (
    flagged_cases_from_primary_feedback,
    labels_from_feedback,
    primary_pass_freeze,
)
from evaluation.experiments.alignment.reference.feedback_models import FeedbackRecord
from evaluation.experiments.alignment.reference.labeling import labeling_run_id


def _feedback(case: object, suffix: str, value: object) -> FeedbackRecord:
    question_key = case.question_key  # type: ignore[attr-defined]
    return cast(
        "FeedbackRecord",
        SimpleNamespace(
            run_id=labeling_run_id(case),  # type: ignore[arg-type]
            key=f"cam41.{question_key}.{suffix}",
            value=value,
            comment=None,
            created_at=datetime(2026, 10, 1, tzinfo=UTC),
            feedback_source=SimpleNamespace(
                user_name="Cameron Ervin",
                user_id="user-cameron",
                type="app",
                metadata=None,
            ),
        ),
    )


def test_primary_feedback_becomes_a_blind_human_label() -> None:
    case = generate_calibration_cases()[0]
    items = [
        _feedback(case, "label", "true"),
        _feedback(case, "confidence", "high"),
        _feedback(case, "rationale", "The displayed evidence directly satisfies the rubric."),
        _feedback(case, "ambiguous", "false"),
    ]

    labels = labels_from_feedback((case,), items, reviewer="Cameron Ervin")

    assert len(labels) == 1
    assert labels[0].value is True
    assert labels[0].reviewer == "Cameron Ervin"
    assert labels[0].adjudication is None


def test_flagged_primary_feedback_requires_second_pass_adjudication() -> None:
    case = generate_calibration_cases()[0]
    items = [
        _feedback(case, "label", "false"),
        _feedback(case, "confidence", "low"),
        _feedback(case, "rationale", "The boundary is ambiguous."),
        _feedback(case, "ambiguous", "true"),
    ]

    with pytest.raises(ValueError, match="adjudication feedback"):
        labels_from_feedback((case,), items, reviewer="Cameron Ervin")

    assert flagged_cases_from_primary_feedback((case,), items, reviewer="Cameron Ervin") == (
        case.case_id,
    )


def test_conflicting_duplicate_feedback_fails_closed() -> None:
    case = generate_calibration_cases()[0]
    items = [
        _feedback(case, "label", "true"),
        _feedback(case, "label", "false"),
        _feedback(case, "confidence", "high"),
        _feedback(case, "rationale", "First pass."),
        _feedback(case, "ambiguous", "false"),
    ]

    with pytest.raises(ValueError, match="duplicate feedback"):
        labels_from_feedback((case,), items, reviewer="Cameron Ervin")


@pytest.mark.parametrize("value", [1.9, float("nan"), float("inf"), True])
def test_score_feedback_rejects_noncanonical_numeric_values(value: object) -> None:
    case = next(
        item for item in generate_calibration_cases() if item.question_key == "actionability"
    )
    items = [
        _feedback(case, "label", value),
        _feedback(case, "confidence", "high"),
        _feedback(case, "rationale", "The displayed evidence maps to one score."),
        _feedback(case, "ambiguous", "false"),
    ]

    with pytest.raises(ValueError, match="feedback label is invalid"):
        labels_from_feedback((case,), items, reviewer="Cameron Ervin")


def test_primary_freeze_binds_feedback_values_timestamp_and_verified_reviewer() -> None:
    case = generate_calibration_cases()[0]
    items = [
        _feedback(case, "label", "true"),
        _feedback(case, "confidence", "high"),
        _feedback(case, "rationale", "The evidence satisfies the criterion."),
        _feedback(case, "ambiguous", "false"),
    ]

    frozen = primary_pass_freeze((case,), items, reviewer="Cameron Ervin")
    items[2].value = "Changed after the queue was frozen"  # type: ignore[attr-defined]
    changed = primary_pass_freeze((case,), items, reviewer="Cameron Ervin")

    assert frozen.checksum != changed.checksum
    assert frozen.frozen_at == datetime(2026, 10, 1, tzinfo=UTC)
    items[0].feedback_source.user_name = "Another Reviewer"  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="reviewer identity"):
        primary_pass_freeze((case,), items, reviewer="Cameron Ervin")

    items[0].feedback_source.user_name = "Cameron Ervin"  # type: ignore[attr-defined]
    items[0].feedback_source.type = "model"  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="LangSmith annotation"):
        primary_pass_freeze((case,), items, reviewer="Cameron Ervin")


def test_declared_manual_api_feedback_preserves_reviewer_provenance() -> None:
    case = generate_calibration_cases()[0]
    items = [
        _feedback(case, "label", "true"),
        _feedback(case, "confidence", "high"),
        _feedback(case, "rationale", "The displayed evidence satisfies the criterion."),
        _feedback(case, "ambiguous", "false"),
    ]
    for item in items:
        item.feedback_source.type = "api"  # type: ignore[attr-defined]
        item.feedback_source.user_name = None  # type: ignore[attr-defined]
        item.feedback_source.user_id = None  # type: ignore[attr-defined]
        item.feedback_source.metadata = {  # type: ignore[attr-defined]
            "review_method": "manual_rubric_review",
            "reviewer": "CAM-41 designated reviewer",
            "reviewer_id": "cam-41-designated-reviewer-v1",
        }

    frozen = primary_pass_freeze((case,), items, reviewer="CAM-41 designated reviewer")

    assert frozen.reviewer_id == "cam-41-designated-reviewer-v1"


def test_api_feedback_without_manual_review_provenance_is_rejected() -> None:
    case = generate_calibration_cases()[0]
    items = [
        _feedback(case, "label", "true"),
        _feedback(case, "confidence", "high"),
        _feedback(case, "rationale", "The displayed evidence satisfies the criterion."),
        _feedback(case, "ambiguous", "false"),
    ]
    for item in items:
        item.feedback_source.type = "api"  # type: ignore[attr-defined]
        item.feedback_source.metadata = {}  # type: ignore[attr-defined]

    with pytest.raises(ValueError, match="manual rubric-review"):
        primary_pass_freeze((case,), items, reviewer="CAM-41 designated reviewer")


def test_langsmith_offsetless_feedback_timestamp_is_normalized_to_utc() -> None:
    case = generate_calibration_cases()[0]
    items = [
        _feedback(case, "label", "true"),
        _feedback(case, "confidence", "high"),
        _feedback(case, "rationale", "The displayed evidence satisfies the criterion."),
        _feedback(case, "ambiguous", "false"),
    ]
    for item in items:
        item.created_at = datetime(2026, 10, 1)  # type: ignore[attr-defined]

    frozen = primary_pass_freeze((case,), items, reviewer="Cameron Ervin")

    assert frozen.frozen_at == datetime(2026, 10, 1, tzinfo=UTC)
