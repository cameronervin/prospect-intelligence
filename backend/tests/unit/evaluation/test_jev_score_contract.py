"""Focused weighted-score normalization behavior."""

import pytest

from evaluation.contracts.judges import SEMANTIC_JUDGE_PROMPT_REVISION
from evaluation.judges import TypeSafeJevJudge
from tests.unit.evaluation.jev_support import FakeAnswer, FakeResponse, FakeTypeSafeClient


@pytest.mark.asyncio
async def test_score_uses_probabilities_as_canonical_weighting_source() -> None:
    answer = FakeAnswer(
        type="score",
        score=1.5,
        probabilities={index: 0.2 for index in range(5)},
        confidence=0.82,
    )
    result = await TypeSafeJevJudge(FakeTypeSafeClient([FakeResponse(answer)])).evaluate(
        "actionability", {"brief": "synthetic"}
    )
    assert result.value == pytest.approx(3.0)


def test_weighted_score_prompt_contract_retains_accepted_v2_revision() -> None:
    assert SEMANTIC_JUDGE_PROMPT_REVISION == "shared-question-payload-v2-weighted-scores"
