from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from statistics import fmean

from evaluation.experiments.alignment.calibration.metrics import (
    balanced_accuracy,
    canonical_label_key,
)
from evaluation.experiments.alignment.calibration.models import (
    ATTEMPTS_PER_CASE,
    CalibrationAttempt,
    QuestionJudgeSummary,
)
from evaluation.experiments.alignment.contracts import AlignmentSplit
from evaluation.rubrics import QUESTIONS


def _disagreement(
    valid: Sequence[CalibrationAttempt],
    *,
    question_key: str,
) -> tuple[dict[str, float], float | None, float | None, int, int]:
    by_case: dict[str, list[CalibrationAttempt]] = defaultdict(list)
    for attempt in valid:
        by_case[attempt.case_id].append(attempt)
    per_case: dict[str, float] = {}
    order_sensitive: list[bool] = []
    for case_id, attempts in sorted(by_case.items()):
        counts = Counter(
            canonical_label_key(question_key, attempt.predicted_value) for attempt in attempts
        )
        per_case[case_id] = 1.0 - max(counts.values()) / len(attempts)
        by_order: dict[tuple[str, ...], list[CalibrationAttempt]] = defaultdict(list)
        for attempt in attempts:
            if attempt.option_order:
                by_order[attempt.option_order].append(attempt)
        repeated = [(order, values) for order, values in by_order.items() if len(values) >= 2]
        if repeated:
            baseline_order, baseline = min(
                repeated,
                key=lambda item: min(attempt.attempt_index for attempt in item[1]),
            )
            baseline_values = {
                canonical_label_key(question_key, attempt.predicted_value) for attempt in baseline
            }
            alternatives = [
                attempt
                for order, values in by_order.items()
                if order != baseline_order
                for attempt in values
            ]
            if len(baseline_values) == 1 and alternatives:
                baseline_value = next(iter(baseline_values))
                order_sensitive.append(
                    any(
                        canonical_label_key(question_key, attempt.predicted_value) != baseline_value
                        for attempt in alternatives
                    )
                )
    return (
        per_case,
        fmean(per_case.values()) if per_case else None,
        fmean(order_sensitive) if order_sensitive else None,
        sum(order_sensitive),
        len(order_sensitive),
    )


def _summarize_group(
    attempts: Sequence[CalibrationAttempt],
    *,
    question_key: str,
    split: AlignmentSplit,
    judge_key: str,
    expected_case_ids: Sequence[str],
) -> QuestionJudgeSummary:
    expected_ids = set(expected_case_ids)
    if len(expected_ids) != len(expected_case_ids):
        raise ValueError("expected calibration case IDs must be unique")
    case_hashes: dict[str, str] = {}
    for attempt in attempts:
        if (
            attempt.question_key != question_key
            or attempt.split != split
            or attempt.judge_key != judge_key
            or attempt.case_id not in expected_ids
        ):
            raise ValueError("calibration attempt is outside the expected inventory")
        prior = case_hashes.setdefault(attempt.case_id, attempt.state_hash)
        if prior != attempt.state_hash:
            raise ValueError("calibration attempts conflict on projected-state hash")
    identities = {(attempt.case_id, attempt.attempt_index) for attempt in attempts}
    if len(identities) != len(attempts):
        raise ValueError("calibration attempts contain duplicate case/attempt identities")
    expected = len(expected_ids) * ATTEMPTS_PER_CASE
    valid = [
        attempt
        for attempt in attempts
        if attempt.status == "valid" and attempt.predicted_value is not None
    ]
    exact = (
        sum(
            canonical_label_key(question_key, attempt.predicted_value)
            == canonical_label_key(question_key, attempt.human_label)
            for attempt in valid
        )
        / len(valid)
        if valid
        else None
    )
    confusion_mutable: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for attempt in valid:
        confusion_mutable[canonical_label_key(question_key, attempt.human_label)][
            canonical_label_key(question_key, attempt.predicted_value)
        ] += 1
    confusion = {
        actual: dict(sorted(predictions.items()))
        for actual, predictions in sorted(confusion_mutable.items())
    }
    balanced, class_imbalance = balanced_accuracy(question_key, valid)
    question = QUESTIONS[question_key]
    errors: list[float] = []
    if question.kind == "score":
        for attempt in valid:
            prediction = attempt.predicted_value
            if isinstance(prediction, int | float) and not isinstance(prediction, bool):
                errors.append(abs(float(prediction) - float(attempt.human_label)))
    per_case, disagreement, sensitivity, sensitive_cases, sensitivity_eligible = _disagreement(
        valid, question_key=question_key
    )
    costs = [
        attempt.estimated_cost_usd for attempt in attempts if attempt.estimated_cost_usd is not None
    ]
    alternate_expected = (
        len(expected_ids) * (ATTEMPTS_PER_CASE - 2) if question.kind != "noul" else 0
    )
    alternate_observed = sum(
        attempt.status == "valid"
        and attempt.predicted_value is not None
        and bool(attempt.option_order)
        and attempt.attempt_index >= 2
        for attempt in attempts
    )
    return QuestionJudgeSummary(
        question_key=question_key,
        split=split,
        judge_key=judge_key,
        expected_attempts=expected,
        valid_attempts=len(valid),
        unavailable_attempts=expected - len(valid),
        coverage=len(valid) / expected,
        exact_agreement=exact,
        confusion=confusion,
        balanced_accuracy=balanced,
        class_imbalance=class_imbalance,
        mean_absolute_error=fmean(errors) if errors else None,
        within_one_agreement=(
            sum(error <= 1.0 for error in errors) / len(errors) if errors else None
        ),
        per_case_disagreement=per_case,
        run_to_run_disagreement=disagreement,
        order_sensitivity=sensitivity,
        order_sensitive_cases=sensitive_cases,
        order_sensitive_eligible_cases=sensitivity_eligible,
        alternate_order_observations=alternate_observed,
        alternate_order_expected=alternate_expected,
        alternate_order_coverage=(
            alternate_observed / alternate_expected if alternate_expected else None
        ),
        total_cost_usd=sum(costs) if len(costs) == expected else None,
        reported_cost_usd=sum(costs),
        costed_attempts=len(costs),
        cost_unavailable_attempts=expected - len(costs),
        cost_coverage=len(costs) / expected,
        total_latency_seconds=sum(attempt.latency_seconds for attempt in attempts),
    )


def summarize_attempts(
    attempts: Sequence[CalibrationAttempt],
    *,
    expected_case_ids: Mapping[tuple[str, AlignmentSplit], Sequence[str]] | None = None,
    judge_keys: Sequence[str] | None = None,
) -> tuple[QuestionJudgeSummary, ...]:
    groups: dict[tuple[str, AlignmentSplit, str], list[CalibrationAttempt]] = defaultdict(list)
    for attempt in attempts:
        if not attempt.case_id or not attempt.judge_key:
            raise ValueError("calibration attempt identifiers must be non-empty")
        if not 0 <= attempt.attempt_index < ATTEMPTS_PER_CASE:
            raise ValueError("calibration attempt index is outside the three-run matrix")
        groups[(attempt.question_key, attempt.split, attempt.judge_key)].append(attempt)
    inventory: dict[tuple[str, AlignmentSplit], Sequence[str]]
    if expected_case_ids is None:
        inventory = {
            (question_key, split): tuple(sorted({item.case_id for item in values}))
            for (question_key, split, _judge), values in groups.items()
        }
    else:
        inventory = dict(expected_case_ids)
    if judge_keys is None:
        expected_judges = tuple(sorted({attempt.judge_key for attempt in attempts}))
    else:
        expected_judges = tuple(judge_keys)
    if not inventory or not expected_judges or len(expected_judges) != len(set(expected_judges)):
        raise ValueError("expected calibration inventory and judges must be non-empty and unique")
    expected_group_keys: set[tuple[str, AlignmentSplit, str]] = {
        (question_key, split, judge_key)
        for (question_key, split) in inventory
        for judge_key in expected_judges
    }
    if set(groups) - expected_group_keys:
        raise ValueError("calibration attempts contain an unexpected question, split, or judge")
    return tuple(
        _summarize_group(
            groups[key],
            question_key=key[0],
            split=key[1],
            judge_key=key[2],
            expected_case_ids=inventory[(key[0], key[1])],
        )
        for key in sorted(expected_group_keys)
    )
