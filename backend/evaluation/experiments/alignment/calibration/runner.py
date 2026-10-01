"""Provider-neutral execution of the three-run calibration matrix."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from evaluation.contracts.judges import SemanticJudge, state_sha256
from evaluation.experiments.alignment.calibration.models import (
    ATTEMPTS_PER_CASE,
    CalibrationAttempt,
)
from evaluation.experiments.alignment.contracts import (
    AlignmentSplit,
    CalibrationCase,
    CalibrationLabel,
)
from evaluation.rubrics import QUESTIONS


@dataclass(frozen=True, slots=True)
class CalibrationInput:
    case_id: str
    state_hash: str
    question_key: str
    split: AlignmentSplit
    state: Mapping[str, object]
    human_label: bool | str | int | float


def calibration_inputs(
    cases: Sequence[CalibrationCase], labels: Sequence[CalibrationLabel]
) -> tuple[CalibrationInput, ...]:
    """Join validated cases and labels, preferring a completed adjudication."""

    by_case = {label.case_id: label for label in labels}
    if len(by_case) != len(labels):
        raise ValueError("calibration labels contain duplicate case IDs")
    inputs: list[CalibrationInput] = []
    for case in cases:
        try:
            label = by_case[case.case_id]
        except KeyError as error:
            raise ValueError(f"calibration label is missing for case {case.case_id}") from error
        if label.question_key != case.question_key or label.state_hash != case.state_hash:
            raise ValueError(f"calibration label does not match case {case.case_id}")
        value = label.adjudication.value if label.adjudication is not None else label.value
        inputs.append(
            CalibrationInput(
                case_id=case.case_id,
                state_hash=case.state_hash,
                question_key=case.question_key,
                split=case.split,
                state=dict(case.state),
                human_label=value,
            )
        )
    if len(inputs) != len(labels):
        raise ValueError("calibration labels contain cases outside the calibration set")
    return tuple(inputs)


def deterministic_option_order(question_key: str, attempt_index: int) -> tuple[str, ...] | None:
    """Return a repeated baseline plus one permutation for attribution."""

    if not 0 <= attempt_index < ATTEMPTS_PER_CASE:
        raise ValueError("attempt index is outside the three-run matrix")
    try:
        question = QUESTIONS[question_key]
    except KeyError as error:
        raise ValueError(f"unknown semantic question: {question_key}") from error
    if question.kind == "noul":
        return None
    options = question.options
    if attempt_index <= 1:
        return options
    shift = attempt_index - 1
    return options[shift:] + options[:shift]


async def run_calibration(
    *,
    inputs: Sequence[CalibrationInput],
    judges: Mapping[str, SemanticJudge],
) -> tuple[CalibrationAttempt, ...]:
    """Run every judge independently; provider errors remain unavailable evidence."""

    if not inputs:
        raise ValueError("at least one calibration input is required")
    if not judges or any(not key.strip() for key in judges):
        raise ValueError("at least one named calibration judge is required")
    attempts: list[CalibrationAttempt] = []
    for item in inputs:
        if state_sha256(item.state) != item.state_hash:
            raise ValueError(f"calibration input state hash mismatch for case {item.case_id}")
        for judge_key, judge in judges.items():
            for attempt_index in range(ATTEMPTS_PER_CASE):
                order = deterministic_option_order(item.question_key, attempt_index)
                started = time.perf_counter()
                try:
                    decision = await judge.evaluate(
                        item.question_key,
                        item.state,
                        option_order=order,
                    )
                    if decision.state_hash != item.state_hash:
                        raise ValueError(
                            "judge decision state hash does not match calibration input"
                        )
                    if decision.question_key != item.question_key:
                        raise ValueError("judge decision question does not match calibration input")
                    if decision.option_order != (order or ()):
                        raise ValueError(
                            "judge decision option order does not match requested order"
                        )
                except Exception as error:
                    attempts.append(
                        CalibrationAttempt(
                            case_id=item.case_id,
                            state_hash=item.state_hash,
                            question_key=item.question_key,
                            split=item.split,
                            judge_key=judge_key,
                            attempt_index=attempt_index,
                            option_order=order or (),
                            human_label=item.human_label,
                            predicted_value=None,
                            status="unavailable",
                            latency_seconds=time.perf_counter() - started,
                            estimated_cost_usd=None,
                            error_type=type(error).__name__,
                        )
                    )
                    continue
                attempts.append(
                    CalibrationAttempt(
                        case_id=item.case_id,
                        state_hash=item.state_hash,
                        question_key=item.question_key,
                        split=item.split,
                        judge_key=judge_key,
                        attempt_index=attempt_index,
                        option_order=decision.option_order,
                        human_label=item.human_label,
                        predicted_value=decision.value,
                        status="valid",
                        latency_seconds=decision.latency_seconds,
                        estimated_cost_usd=decision.estimated_cost_usd,
                    )
                )
    return tuple(attempts)
