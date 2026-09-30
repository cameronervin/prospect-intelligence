"""LangSmith-native semantic evaluator composition."""

from collections.abc import Mapping
from typing import cast

import pytest
from langsmith.evaluation import EvaluationResult

from evaluation.contracts.judges import JudgeDecision, SemanticJudge
from evaluation.evaluators.semantic import semantic_evaluators


class RecordingJudge(SemanticJudge):
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, object], tuple[str, ...] | None]] = []

    async def evaluate(
        self,
        question_key: str,
        state: Mapping[str, object],
        *,
        option_order: tuple[str, ...] | None = None,
    ) -> JudgeDecision:
        self.calls.append((question_key, state, option_order))
        values: dict[str, bool | str | float] = {
            "claim_supported": True,
            "internal_data_leak": True,
            "draft_matches_brief": True,
            "next_step": "new_lane_pitch",
            "entity_resolution_ok": True,
            "actionability": 4.0,
            "tone_fit": 5.0,
        }
        probabilities = (
            {
                "new_lane_pitch": 0.7,
                "expand_existing_lanes": 0.1,
                "not_a_fit": 0.1,
                "needs_more_data": 0.1,
            }
            if question_key == "next_step"
            else {"yes": 0.8, "no": 0.2}
        )
        return JudgeDecision(
            question_key=question_key,
            rubric_version="semantic-v1",
            value=values[question_key],
            probabilities=probabilities,
            certainty=0.6,
            certainty_source="provider_confidence",
            requested_model="jev-1.13.0",
            resolved_model="jev-1.13.0",
            resolved_model_source="provider_response",
            option_order=option_order or (),
            state_hash=f"hash-{len(self.calls)}",
            latency_seconds=0.01,
            request_id=f"request-{len(self.calls)}",
            input_tokens=10,
            cached_input_tokens=None,
            output_tokens=1,
            token_count_source="provider_final",
            retries=0,
            retry_count_source="provider_usage",
            pricing_version="test-pricing-v1",
            estimated_cost_usd=0.000001,
        )


def _outputs() -> dict[str, object]:
    return {
        "semantic_observations": {
            "claim_supported": [
                {
                    "claim": "First claim",
                    "excerpt": "First support",
                    "citation_ids": ["ev_111111111111111111111111"],
                },
                {
                    "claim": "Second claim",
                    "excerpt": "Second support",
                    "citation_ids": ["ev_222222222222222222222222"],
                },
            ],
            "internal_data_leak": {"draft": "Synthetic draft"},
            "draft_matches_brief": {"brief": "Synthetic brief", "draft": "Synthetic draft"},
            "next_step": {"brief": "Synthetic brief"},
            "entity_resolution_ok": {
                "account_name": "Synthetic Foods",
                "resolved_profile": "Account name: Synthetic Foods.",
            },
            "actionability": {"brief": "Synthetic brief"},
            "tone_fit": {
                "draft": "Synthetic draft",
                "rep_preferences": "Prefer concise outreach.",
            },
        }
    }


def _metadata(result: EvaluationResult) -> Mapping[str, object]:
    return cast(
        "Mapping[str, object]",
        result.metadata or {},  # pyright: ignore[reportUnknownMemberType]
    )


@pytest.mark.asyncio
async def test_semantic_suite_returns_native_results_with_expected_scoring() -> None:
    judge = RecordingJudge()
    evaluators = semantic_evaluators(judge)
    results = [
        await evaluator(_outputs(), {"expected_next_step": "new_lane_pitch"})
        for evaluator in evaluators
    ]

    assert all(isinstance(result, EvaluationResult) for result in results)
    assert {result.key: result.score for result in results} == {
        "claim_supported": 0.8,
        "internal_data_leak": pytest.approx(0.2),
        "draft_matches_brief": 0.8,
        "next_step": 0.7,
        "entity_resolution_ok": 0.8,
        "actionability": 4.0,
        "tone_fit": 5.0,
    }
    assert [call[0] for call in judge.calls].count("claim_supported") == 2
    for result in results:
        metadata = _metadata(result)
        assert "state_hash" in repr(metadata)
        assert "semantic-v1" in repr(metadata)
        assert "probabilities" in repr(metadata)
        assert "test-pricing-v1" in repr(metadata)
        assert "Synthetic brief" not in repr(metadata)
        assert "Synthetic draft" not in repr(metadata)


@pytest.mark.asyncio
async def test_claim_supported_vacuously_passes_when_there_are_no_qualitative_claims() -> None:
    judge = RecordingJudge()
    outputs = _outputs()
    observations = dict(cast("Mapping[str, object]", outputs["semantic_observations"]))
    observations["claim_supported"] = []
    outputs["semantic_observations"] = observations
    evaluator = semantic_evaluators(judge)[0]

    result = await evaluator(outputs, {"expected_next_step": "new_lane_pitch"})

    assert result.score == 1.0
    assert _metadata(result) == {"checked_count": 0, "not_applicable": True}
    assert judge.calls == []


class FailingJudge(SemanticJudge):
    async def evaluate(
        self,
        question_key: str,
        state: Mapping[str, object],
        *,
        option_order: tuple[str, ...] | None = None,
    ) -> JudgeDecision:
        del question_key, state, option_order
        raise RuntimeError("raw provider body must not escape")


@pytest.mark.asyncio
async def test_provider_failure_returns_missing_score_with_sanitized_metadata() -> None:
    evaluator = semantic_evaluators(FailingJudge())[1]

    result = await evaluator(_outputs(), {"expected_next_step": "new_lane_pitch"})

    assert result.score is None
    assert _metadata(result) == {"error_type": "RuntimeError", "status": "unavailable"}
    assert "raw provider body" not in repr(result)


@pytest.mark.asyncio
async def test_unresolved_claim_and_entity_fail_closed_without_a_provider_call() -> None:
    judge = RecordingJudge()
    outputs = _outputs()
    observations = dict(cast("Mapping[str, object]", outputs["semantic_observations"]))
    observations["claim_supported"] = [
        {"claim": "Unresolved claim", "excerpt": "support", "citation_ids": ["bad-id"]}
    ]
    observations["entity_resolution_ok"] = {
        "account_name": "Synthetic Foods",
        "resolved_profile": "",
    }
    outputs["semantic_observations"] = observations
    claim, *_, entity, _, _ = semantic_evaluators(judge)

    claim_result = await claim(outputs, {"expected_next_step": "new_lane_pitch"})
    entity_result = await entity(outputs, {"expected_next_step": "new_lane_pitch"})

    assert claim_result.score == 0.0
    assert _metadata(claim_result) == {"status": "unresolved_citation"}
    assert entity_result.score == 0.0
    assert _metadata(entity_result) == {"status": "unresolved_profile"}
    assert judge.calls == []


@pytest.mark.asyncio
async def test_canary_is_rejected_before_any_semantic_provider_call() -> None:
    judge = RecordingJudge()
    outputs = _outputs()
    observations = dict(cast("Mapping[str, object]", outputs["semantic_observations"]))
    observations["internal_data_leak"] = {"draft": "Echo PLANTED-CANARY"}
    outputs["semantic_observations"] = observations
    evaluator = semantic_evaluators(judge)[1]

    result = await evaluator(outputs, {"injection_canary": "planted-canary"})

    assert result.score is None
    assert _metadata(result) == {"status": "injection_canary_rejected"}
    assert judge.calls == []


@pytest.mark.asyncio
async def test_tone_fit_without_preferences_is_explicitly_not_applicable() -> None:
    judge = RecordingJudge()
    outputs = _outputs()
    observations = dict(cast("Mapping[str, object]", outputs["semantic_observations"]))
    observations["tone_fit"] = None
    outputs["semantic_observations"] = observations
    evaluator = semantic_evaluators(judge)[-1]

    result = await evaluator(outputs, {"expected_next_step": "new_lane_pitch"})

    assert result.score is None
    assert _metadata(result) == {"not_applicable": True}
    assert judge.calls == []
