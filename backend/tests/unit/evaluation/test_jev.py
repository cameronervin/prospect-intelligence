"""Semantic-judge rubric and bounded-state contract tests."""

import pytest

from evaluation.contracts import state_sha256
from evaluation.judges import (
    JEV_MODEL_VERSION,
    OPENAI_COMPARISON_MODEL,
    OpenAIComparisonJudge,
    TypeSafeJevJudge,
)
from evaluation.rubrics import QUESTIONS, RUBRIC_VERSION
from tests.unit.evaluation.jev_support import FakeTypeSafeClient


def test_all_seven_typed_questions_are_exact_and_version_pinned() -> None:
    assert JEV_MODEL_VERSION == "jev-1.13.0"
    assert OPENAI_COMPARISON_MODEL == "gpt-5.6-sol"
    assert RUBRIC_VERSION == "semantic-v1"
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
    assert QUESTIONS["next_step"].options == (
        "expand_existing_lanes",
        "new_lane_pitch",
        "not_a_fit",
        "needs_more_data",
    )
    assert QUESTIONS["actionability"].criteria == (
        "Not actionable: no concrete recommendation or next step.",
        "Weakly actionable: a vague recommendation with little usable detail.",
        "Moderately actionable: a clear recommendation but important details are missing.",
        "Highly actionable: a clear recommendation and practical next step.",
        "Immediately actionable: specific, prioritized guidance a sales rep can use now.",
    )


def test_state_hash_is_canonical_and_does_not_expose_state() -> None:
    first = state_sha256({"b": [2, 1], "a": "secret"})
    second = state_sha256({"a": "secret", "b": [2, 1]})
    assert first == second
    assert len(first) == 64
    assert "secret" not in first


@pytest.mark.asyncio
async def test_state_is_projected_and_strictly_bounded() -> None:
    judge = TypeSafeJevJudge(FakeTypeSafeClient([]))
    with pytest.raises(ValueError, match="missing state fields"):
        await judge.evaluate("tone_fit", {"draft": "synthetic"})
    with pytest.raises(ValueError, match="option order"):
        await judge.evaluate("next_step", {"brief": "synthetic"}, option_order=("bad",))
    with pytest.raises(ValueError, match="JSON-compatible"):
        await judge.evaluate("internal_data_leak", {"draft": object()})
    with pytest.raises(ValueError, match="text"):
        await judge.evaluate("internal_data_leak", {"draft": {"nested": "value"}})
    with pytest.raises(ValueError, match="string exceeds"):
        await judge.evaluate("internal_data_leak", {"draft": "x" * 8_001})


def test_live_judges_require_nonempty_credentials() -> None:
    with pytest.raises(ValueError, match="TypeSafe API key"):
        TypeSafeJevJudge.from_api_key("  ")
    with pytest.raises(ValueError, match="OpenAI API key"):
        OpenAIComparisonJudge.from_api_key("")
