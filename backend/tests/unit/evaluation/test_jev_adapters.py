"""Provider adapter, response validation, retry, and accounting tests."""

import math
from itertools import permutations

import pytest

from evaluation.contracts import JudgeProtocolError, state_sha256
from evaluation.judges import (
    JEV_MODEL_VERSION,
    JEV_PRICING,
    OPENAI_COMPARISON_MODEL,
    OPENAI_COMPARISON_PRICING,
    OpenAIComparisonJudge,
    TypeSafeJevJudge,
)
from evaluation.rubrics import QUESTIONS, RUBRIC_VERSION
from tests.unit.evaluation.jev_support import (
    FakeAnswer,
    FakeResponse,
    FakeTypeSafeClient,
    FakeUsage,
)


@pytest.mark.asyncio
async def test_noul_is_normalized_with_derived_certainty_and_cost() -> None:
    client = FakeTypeSafeClient(
        [
            FakeResponse(
                FakeAnswer(type="noul", noul=0.8),
                usage=FakeUsage(output_tokens=None),
            )
        ]
    )
    result = await TypeSafeJevJudge(client).evaluate(
        "internal_data_leak", {"draft": "synthetic", "secret": "not-sent"}
    )
    assert result.value is True
    assert result.probabilities == {"yes": 0.8, "no": pytest.approx(0.2)}
    assert result.certainty == pytest.approx(0.6)
    assert result.certainty_source == "derived_noul_probability"
    assert result.rubric_version == RUBRIC_VERSION
    assert result.pricing_version == JEV_PRICING.version
    assert result.retries == 0
    assert result.retry_count_source == "sdk_policy"
    assert result.requested_model == result.resolved_model == JEV_MODEL_VERSION
    assert result.request_id == "req_test"
    assert result.estimated_cost_usd == pytest.approx(
        1_000 * JEV_PRICING.input_usd_per_million / 1_000_000
    )
    assert result.state_hash == state_sha256({"draft": "synthetic"})
    assert client.calls[0]["state"] == {"draft": "synthetic"}
    retry = client.calls[0]["retry"]
    assert retry.max_retries == 2
    assert retry.timeout == 30
    assert retry.http_statuses == {408, 429, *range(500, 600)}
    assert client.calls[0]["timeout"] == 30


@pytest.mark.asyncio
async def test_choice_preserves_option_order_probabilities_and_confidence() -> None:
    options = ("needs_more_data", "not_a_fit", "new_lane_pitch", "expand_existing_lanes")
    answer = FakeAnswer(
        type="choice",
        choice="not_a_fit",
        probabilities={option: 0.25 for option in options},
        confidence=0.7,
    )
    client = FakeTypeSafeClient([FakeResponse(answer)])
    result = await TypeSafeJevJudge(client).evaluate(
        "next_step", {"brief": "synthetic"}, option_order=options
    )
    assert result.value == "not_a_fit"
    assert result.option_order == options
    assert result.certainty == 0.7
    assert tuple(client.calls[0]["questions"]["decision"].criteria) == options


@pytest.mark.asyncio
async def test_score_is_shifted_from_provider_zero_based_scale() -> None:
    answer = FakeAnswer(
        type="score",
        score=3,
        probabilities={index: 0.2 for index in range(5)},
        confidence=0.82,
    )
    result = await TypeSafeJevJudge(FakeTypeSafeClient([FakeResponse(answer)])).evaluate(
        "actionability", {"brief": "synthetic"}
    )
    assert result.value == 4
    assert result.option_order == ("1", "2", "3", "4", "5")
    assert result.probabilities == {str(index): 0.2 for index in range(1, 6)}


@pytest.mark.asyncio
async def test_every_next_step_option_permutation_is_preserved() -> None:
    orders = list(permutations(QUESTIONS["next_step"].options))
    responses = [
        FakeResponse(
            FakeAnswer(
                type="choice",
                choice=order[0],
                probabilities={option: 0.25 for option in order},
                confidence=0.5,
            )
        )
        for order in orders
    ]
    client = FakeTypeSafeClient(responses)
    judge = TypeSafeJevJudge(client)
    for order in orders:
        decision = await judge.evaluate("next_step", {"brief": "synthetic"}, option_order=order)
        assert decision.option_order == order
        assert tuple(client.calls[-1]["questions"]["decision"].criteria) == order


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer,model,match",
    [
        (FakeAnswer(type="choice", choice="x"), JEV_MODEL_VERSION, "type"),
        (FakeAnswer(type="noul", noul=math.nan), JEV_MODEL_VERSION, "finite"),
        (FakeAnswer(type="noul", noul=1.1), JEV_MODEL_VERSION, "between"),
        (FakeAnswer(type="noul", noul=0.5), "jev-latest", "model"),
    ],
)
async def test_jev_rejects_wrong_type_model_and_invalid_probability(
    answer: FakeAnswer, model: str, match: str
) -> None:
    judge = TypeSafeJevJudge(FakeTypeSafeClient([FakeResponse(answer, model=model)]))
    with pytest.raises(JudgeProtocolError, match=match):
        await judge.evaluate("internal_data_leak", {"draft": "synthetic"})


@pytest.mark.asyncio
async def test_choice_rejects_probability_keys_that_do_not_match_options() -> None:
    answer = FakeAnswer(
        type="choice",
        choice="not_a_fit",
        probabilities={"not_a_fit": 1.0},
        confidence=0.8,
    )
    with pytest.raises(JudgeProtocolError, match="probability options"):
        await TypeSafeJevJudge(FakeTypeSafeClient([FakeResponse(answer)])).evaluate(
            "next_step", {"brief": "synthetic"}
        )


@pytest.mark.asyncio
async def test_comparison_cost_accounts_for_cached_input_tokens() -> None:
    usage = FakeUsage(
        input_tokens=1_000,
        cached_input_tokens=200,
        output_tokens=10,
        n_retries=1,
        n_retries_malformed_structure=1,
    )
    response = FakeResponse(
        FakeAnswer(type="noul", noul=0.6), model=OPENAI_COMPARISON_MODEL, usage=usage
    )
    result = await OpenAIComparisonJudge(FakeTypeSafeClient([response])).evaluate(
        "internal_data_leak", {"draft": "synthetic"}
    )
    expected = (
        800 * OPENAI_COMPARISON_PRICING.input_usd_per_million
        + 200 * OPENAI_COMPARISON_PRICING.cached_input_usd_per_million
        + 10 * OPENAI_COMPARISON_PRICING.output_usd_per_million
    ) / 1_000_000
    assert result.cached_input_tokens == 200
    assert result.retries == 2
    assert result.retry_count_source == "provider_usage"
    assert result.estimated_cost_usd == pytest.approx(expected)


@pytest.mark.asyncio
async def test_comparison_cost_uses_total_tokens_across_adapter_retries() -> None:
    usage = FakeUsage(
        input_tokens=1_000,
        cached_input_tokens=200,
        output_tokens=10,
        input_tokens_total=1_200,
        output_tokens_total=15,
        n_retries=1,
    )
    response = FakeResponse(
        FakeAnswer(type="noul", noul=0.6), model=OPENAI_COMPARISON_MODEL, usage=usage
    )
    result = await OpenAIComparisonJudge(FakeTypeSafeClient([response])).evaluate(
        "internal_data_leak", {"draft": "synthetic"}
    )
    expected = (
        1_200 * OPENAI_COMPARISON_PRICING.input_usd_per_million
        + 15 * OPENAI_COMPARISON_PRICING.output_usd_per_million
    ) / 1_000_000
    assert result.token_count_source == "provider_total"
    assert result.cached_input_tokens is None
    assert result.estimated_cost_usd == pytest.approx(expected)
