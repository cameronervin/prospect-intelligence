"""Credential-free CAM-41/CAM-50 calibration self-test."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from evaluation.contracts.judges import JudgeDecision, state_sha256
from evaluation.experiments.alignment.calibration.models import QuestionJudgeSummary
from evaluation.experiments.alignment.calibration.policy import recommend_alignment
from evaluation.experiments.alignment.calibration.results import summarize_attempts
from evaluation.experiments.alignment.calibration.runner import (
    calibration_inputs,
    run_calibration,
)
from evaluation.experiments.alignment.contracts import CalibrationCase, CalibrationLabel
from evaluation.experiments.alignment.reference.cases import generate_calibration_cases
from evaluation.experiments.alignment.reference.labels import validate_calibration_labels
from evaluation.rubrics import QUESTIONS, RUBRIC_VERSION


def _expected_label(case: CalibrationCase) -> bool | str | int:
    for stratum in case.strata:
        if stratum == "positive":
            return True
        if stratum == "negative":
            return False
        if stratum.startswith("class:"):
            return stratum.removeprefix("class:")
        if stratum.startswith("score:"):
            return int(stratum.removeprefix("score:"))
    raise ValueError(f"case has no planted calibration label: {case.case_id}")


def synthetic_labels(cases: Sequence[CalibrationCase]) -> tuple[CalibrationLabel, ...]:
    labeled_at = datetime(2026, 10, 1, tzinfo=UTC)
    return tuple(
        CalibrationLabel(
            case_id=case.case_id,
            question_key=case.question_key,
            state_hash=case.state_hash,
            value=_expected_label(case),
            confidence="high",
            rationale="Credential-free planted label for the local calibration self-test.",
            ambiguous=False,
            reviewer="local-self-test",
            labeled_at=labeled_at,
            label_set_version="cam-41-labels-v1",
        )
        for case in cases
    )


class _PerfectJudge:
    def __init__(self, labels: Mapping[str, bool | str | int], *, model: str) -> None:
        self._labels = labels
        self._model = model

    async def evaluate(
        self,
        question_key: str,
        state: Mapping[str, object],
        *,
        option_order: tuple[str, ...] | None = None,
    ) -> JudgeDecision:
        state_hash = state_sha256(state)
        value = self._labels[state_hash]
        order = option_order or QUESTIONS[question_key].options
        return JudgeDecision(
            question_key=question_key,
            rubric_version=RUBRIC_VERSION,
            value=value,
            probabilities={},
            certainty=1.0,
            certainty_source="provider_confidence",
            requested_model=self._model,
            resolved_model=self._model,
            resolved_model_source="adapter_configuration",
            option_order=order,
            state_hash=state_hash,
            latency_seconds=0.001,
            request_id=None,
            input_tokens=1,
            cached_input_tokens=0,
            output_tokens=1,
            token_count_source="provider_final",
            retries=0,
            retry_count_source="provider_usage",
            pricing_version="self-test",
            estimated_cost_usd=0.0,
        )


def _summary(
    summaries: Sequence[QuestionJudgeSummary], question_key: str, judge_key: str
) -> QuestionJudgeSummary:
    matches = [
        summary
        for summary in summaries
        if summary.question_key == question_key
        and summary.judge_key == judge_key
        and summary.split == "holdout"
    ]
    if len(matches) != 1:
        raise RuntimeError("self-test holdout summary coverage drift")
    return matches[0]


async def run_self_test() -> tuple[int, int]:
    """Exercise the complete local matrix without constructing an external client."""

    cases = generate_calibration_cases()
    labels = validate_calibration_labels(cases, synthetic_labels(cases))
    planted = {label.state_hash: label.value for label in labels}
    inputs = calibration_inputs(cases, labels)
    attempts = await run_calibration(
        inputs=inputs,
        judges={
            "jev": _PerfectJudge(planted, model="jev-self-test"),
            "sol": _PerfectJudge(planted, model="sol-self-test"),
        },
    )
    inventory = {
        (question_key, split): tuple(
            item.case_id
            for item in inputs
            if item.question_key == question_key and item.split == split
        )
        for question_key in QUESTIONS
        for split in ("alignment", "holdout")
    }
    summaries = summarize_attempts(
        attempts,
        expected_case_ids=inventory,  # type: ignore[arg-type]
        judge_keys=("jev", "sol"),
    )
    for question_key in QUESTIONS:
        recommendation = recommend_alignment(
            jev=_summary(summaries, question_key, "jev"),
            sol=_summary(summaries, question_key, "sol"),
        )
        if recommendation.recommendation != "retain":
            raise RuntimeError("credential-free calibration policy self-test failed")
    return len(cases), len(attempts)


__all__ = ["run_self_test", "synthetic_labels"]
