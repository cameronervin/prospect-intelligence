"""Credential-free calibration runner tests."""

from collections.abc import Mapping

import pytest

from evaluation.contracts.judges import JudgeDecision, state_sha256
from evaluation.experiments.alignment.calibration.runner import (
    ATTEMPTS_PER_CASE,
    CalibrationInput,
    deterministic_option_order,
    run_calibration,
)


class _Judge:
    def __init__(
        self,
        *,
        value: object = True,
        error: Exception | None = None,
        state_hash: str | None = None,
    ) -> None:
        self.value = value
        self.error = error
        self.state_hash = state_hash
        self.calls: list[tuple[str, tuple[str, ...] | None]] = []

    async def evaluate(
        self,
        question_key: str,
        state: Mapping[str, object],
        *,
        option_order: tuple[str, ...] | None = None,
    ) -> JudgeDecision:
        self.calls.append((question_key, option_order))
        if self.error is not None:
            raise self.error
        return JudgeDecision(
            question_key=question_key,
            rubric_version="semantic-v1",
            value=self.value,  # type: ignore[arg-type]
            probabilities={},
            certainty=1.0,
            certainty_source="provider_confidence",
            requested_model="fake",
            resolved_model="fake",
            resolved_model_source="adapter_configuration",
            option_order=option_order or (),
            state_hash=self.state_hash or state_sha256(state),
            latency_seconds=0.25,
            request_id=None,
            input_tokens=1,
            cached_input_tokens=None,
            output_tokens=1,
            token_count_source="provider_final",
            retries=0,
            retry_count_source="sdk_policy",
            pricing_version="test",
            estimated_cost_usd=0.01,
        )


def _input(question_key: str = "internal_data_leak") -> CalibrationInput:
    state = {"draft": "synthetic"} if question_key != "next_step" else {"brief": "x"}
    if question_key == "actionability":
        state = {"brief": "x"}
    return CalibrationInput(
        case_id="case-1",
        state_hash=state_sha256(state),
        question_key=question_key,
        split="holdout",
        state=state,
        human_label=4.0 if question_key == "actionability" else True,
    )


def test_deterministic_orders_cover_choice_and_score_without_changing_labels() -> None:
    choice = [deterministic_option_order("next_step", index) for index in range(3)]
    scores = [deterministic_option_order("actionability", index) for index in range(3)]
    assert choice[0] == choice[1]
    assert len(set(choice)) == 2
    choice_labels = {
        "expand_existing_lanes",
        "new_lane_pitch",
        "not_a_fit",
        "needs_more_data",
    }
    assert all(set(order or ()) == choice_labels for order in choice)
    assert scores[0] == scores[1]
    assert len(set(scores)) == 2
    assert all(set(order or ()) == {"1", "2", "3", "4", "5"} for order in scores)
    assert deterministic_option_order("internal_data_leak", 0) is None


@pytest.mark.asyncio
async def test_runner_executes_exactly_three_attempts_per_case_and_judge() -> None:
    jev = _Judge()
    sol = _Judge()
    attempts = await run_calibration(inputs=(_input("next_step"),), judges={"jev": jev, "sol": sol})
    assert len(attempts) == 2 * ATTEMPTS_PER_CASE
    assert {attempt.attempt_index for attempt in attempts} == set(range(ATTEMPTS_PER_CASE))
    assert all(attempt.status == "valid" for attempt in attempts)
    assert len(jev.calls) == len(sol.calls) == ATTEMPTS_PER_CASE


@pytest.mark.asyncio
async def test_provider_failure_is_unavailable_and_never_falls_back() -> None:
    unavailable = _Judge(error=RuntimeError("provider down"))
    comparison = _Judge(value=False)
    attempts = await run_calibration(
        inputs=(_input(),), judges={"jev": unavailable, "sol": comparison}
    )
    jev = [attempt for attempt in attempts if attempt.judge_key == "jev"]
    assert len(jev) == ATTEMPTS_PER_CASE
    assert all(
        attempt.status == "unavailable" and attempt.predicted_value is None for attempt in jev
    )
    assert len(unavailable.calls) == ATTEMPTS_PER_CASE
    assert len(comparison.calls) == ATTEMPTS_PER_CASE


@pytest.mark.asyncio
async def test_state_hash_mismatch_cannot_become_valid_evidence() -> None:
    wrong_hash = _Judge(state_hash="f" * 64)
    attempts = await run_calibration(inputs=(_input(),), judges={"jev": wrong_hash})
    assert all(attempt.status == "unavailable" for attempt in attempts)
    assert all(attempt.error_type == "ValueError" for attempt in attempts)
