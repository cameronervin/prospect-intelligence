"""Jev question contract tests."""

import pytest

from evaluation.evaluators.jev import (
    JEV_MODEL_VERSION,
    QUESTIONS,
    CalibrationPlan,
    JevEvaluator,
)


class RecordingJevGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], tuple[str, ...]]] = []

    def evaluate(
        self, *, model: str, question_key: str, state: dict[str, object], options: tuple[str, ...]
    ) -> dict[str, object]:
        self.calls.append((model, state, options))
        return {"value": True, "confidence": 0.9, "question_key": question_key}


def test_all_seven_typed_questions_are_version_pinned() -> None:
    assert JEV_MODEL_VERSION == "jev-1.13.0"
    assert set(QUESTIONS) == {
        "claim_supported",
        "internal_data_leak",
        "draft_matches_brief",
        "next_step",
        "entity_resolution_ok",
        "actionability",
        "tone_fit",
    }
    assert {question.kind for question in QUESTIONS.values()} == {"noul", "choice", "score"}
    assert CalibrationPlan.default().human_labels_per_question == 40
    assert CalibrationPlan.default().judge_repetitions == 5
    assert CalibrationPlan.default().permute_option_order


def test_jev_adapter_receives_only_declared_projected_state() -> None:
    gateway = RecordingJevGateway()
    evaluator = JevEvaluator(gateway)

    result = evaluator.evaluate(
        "internal_data_leak",
        {"draft": "Hello", "raw_web_output": "malicious", "secret": "do-not-send"},
    )

    assert result["value"] is True
    assert gateway.calls == [(JEV_MODEL_VERSION, {"draft": "Hello"}, ())]


def test_jev_adapter_rejects_missing_required_state() -> None:
    with pytest.raises(ValueError, match="missing state fields"):
        JevEvaluator(RecordingJevGateway()).evaluate("tone_fit", {"draft": "Hello"})
