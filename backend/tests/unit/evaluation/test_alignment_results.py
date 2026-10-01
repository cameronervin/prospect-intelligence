"""Calibration aggregation tests."""

import pytest

from evaluation.experiments.alignment.calibration.models import CalibrationAttempt
from evaluation.experiments.alignment.calibration.results import summarize_attempts


def _attempt(
    *,
    case_id: str,
    label: bool | str | float,
    prediction: bool | str | float | None,
    index: int,
    question: str = "internal_data_leak",
    judge: str = "jev",
    order: tuple[str, ...] = (),
) -> CalibrationAttempt:
    return CalibrationAttempt(
        case_id=case_id,
        state_hash="a" * 64,
        question_key=question,
        split="holdout",
        judge_key=judge,
        attempt_index=index,
        option_order=order,
        human_label=label,
        predicted_value=prediction,
        status="valid" if prediction is not None else "unavailable",
        latency_seconds=0.2,
        estimated_cost_usd=0.01,
    )


def test_summary_uses_full_denominator_but_valid_only_agreement_and_confusion() -> None:
    attempts = [
        _attempt(case_id="yes", label=True, prediction=True if i < 2 else None, index=i)
        for i in range(3)
    ] + [_attempt(case_id="no", label=False, prediction=(i == 0), index=i) for i in range(3)]
    summary = summarize_attempts(attempts)[0]
    assert summary.expected_attempts == 6
    assert summary.valid_attempts == 5
    assert summary.unavailable_attempts == 1
    assert summary.coverage == pytest.approx(5 / 6)
    assert summary.exact_agreement == pytest.approx(4 / 5)
    assert summary.confusion["false"]["true"] == 1
    assert summary.balanced_accuracy == pytest.approx((1.0 + 2 / 3) / 2)
    assert summary.total_cost_usd == pytest.approx(0.06)
    assert summary.costed_attempts == 6
    assert summary.cost_unavailable_attempts == 0
    assert summary.cost_coverage == 1.0
    assert summary.total_latency_seconds == pytest.approx(1.2)


def test_balanced_accuracy_is_undefined_when_a_required_class_is_missing() -> None:
    attempts = [_attempt(case_id="yes", label=True, prediction=True, index=i) for i in range(3)]
    summary = summarize_attempts(attempts)[0]
    assert summary.balanced_accuracy is None
    assert summary.class_imbalance is True


def test_score_summary_reports_mae_within_one_disagreement_and_order_sensitivity() -> None:
    predictions = (4.0, 4.0, 3.0)
    orders = (
        ("1", "2", "3", "4", "5"),
        ("1", "2", "3", "4", "5"),
        ("2", "3", "4", "5", "1"),
    )
    attempts = [
        _attempt(
            case_id="score",
            question="actionability",
            label=4.0,
            prediction=value,
            index=index,
            order=orders[index],
        )
        for index, value in enumerate(predictions)
    ]
    summary = summarize_attempts(attempts)[0]
    assert summary.mean_absolute_error == pytest.approx(1 / 3)
    assert summary.within_one_agreement == pytest.approx(1.0)
    assert summary.per_case_disagreement == {"score": pytest.approx(1 / 3)}
    assert summary.order_sensitivity == pytest.approx(1.0)
    assert summary.order_sensitive_cases == 1
    assert summary.order_sensitive_eligible_cases == 1
    assert summary.alternate_order_observations == 1
    assert summary.alternate_order_expected == 1
    assert summary.alternate_order_coverage == 1.0


def test_unstable_repeated_baseline_is_not_eligible_for_order_sensitivity() -> None:
    orders = (
        ("1", "2", "3", "4", "5"),
        ("1", "2", "3", "4", "5"),
        ("2", "3", "4", "5", "1"),
    )
    attempts = [
        _attempt(
            case_id="score",
            question="actionability",
            label=4.0,
            prediction=value,
            index=index,
            order=orders[index],
        )
        for index, value in enumerate((4.0, 5.0, 4.0))
    ]

    summary = summarize_attempts(attempts)[0]

    assert summary.order_sensitive_eligible_cases == 0
    assert summary.order_sensitive_cases == 0
    assert summary.order_sensitivity is None


def test_stability_is_unavailable_when_every_attempt_is_unavailable() -> None:
    attempts = [
        _attempt(case_id="missing", label=True, prediction=None, index=index) for index in range(3)
    ]

    summary = summarize_attempts(attempts)[0]

    assert summary.run_to_run_disagreement is None
    assert summary.order_sensitivity is None


def test_missing_cost_telemetry_is_never_reported_as_measured_zero() -> None:
    attempt = _attempt(case_id="yes", label=True, prediction=True, index=0)
    attempts = [
        attempt,
        *[
            _attempt(case_id="yes", label=True, prediction=True, index=index)
            for index in range(1, 3)
        ],
    ]
    attempts[0] = CalibrationAttempt(
        case_id=attempt.case_id,
        state_hash=attempt.state_hash,
        question_key=attempt.question_key,
        split=attempt.split,
        judge_key=attempt.judge_key,
        attempt_index=attempt.attempt_index,
        option_order=attempt.option_order,
        human_label=attempt.human_label,
        predicted_value=attempt.predicted_value,
        status=attempt.status,
        latency_seconds=attempt.latency_seconds,
        estimated_cost_usd=None,
    )
    summary = summarize_attempts(attempts)[0]
    assert summary.total_cost_usd is None
    assert summary.reported_cost_usd == pytest.approx(0.02)
    assert summary.costed_attempts == 2
    assert summary.cost_unavailable_attempts == 1
    assert summary.cost_coverage == pytest.approx(2 / 3)


def test_expected_inventory_keeps_an_entirely_missing_case_in_coverage_denominator() -> None:
    attempts = [_attempt(case_id="present", label=True, prediction=True, index=i) for i in range(3)]

    summary = summarize_attempts(
        attempts,
        expected_case_ids={("internal_data_leak", "holdout"): ("present", "entirely-missing")},
        judge_keys=("jev",),
    )[0]

    assert summary.expected_attempts == 6
    assert summary.valid_attempts == 3
    assert summary.coverage == 0.5


def test_alternate_order_coverage_includes_an_entirely_missing_case() -> None:
    orders = (
        ("1", "2", "3", "4", "5"),
        ("1", "2", "3", "4", "5"),
        ("2", "3", "4", "5", "1"),
    )
    attempts = [
        _attempt(
            case_id="present",
            question="actionability",
            label=4.0,
            prediction=4.0,
            index=index,
            order=orders[index],
        )
        for index in range(3)
    ]

    summary = summarize_attempts(
        attempts,
        expected_case_ids={("actionability", "holdout"): ("present", "entirely-missing")},
        judge_keys=("jev",),
    )[0]

    assert summary.alternate_order_observations == 1
    assert summary.alternate_order_expected == 2
    assert summary.alternate_order_coverage == 0.5
