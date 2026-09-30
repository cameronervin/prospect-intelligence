"""Application-owned semantic judge contracts and Jev integration."""

import pytest

from app.features.agent_quality.contracts.semantic_judges import (
    JudgeDecision as AppJudgeDecision,
)
from app.features.agent_quality.contracts.semantic_judges import project_state
from app.features.agent_quality.contracts.semantic_states import SemanticObservations
from app.features.agent_quality.domain.semantic_projection import (
    semantic_observations as app_semantic_observations,
)
from app.features.agent_quality.domain.semantic_rubrics import (
    QUESTIONS as APP_QUESTIONS,
)
from app.features.agent_quality.domain.semantic_runtime import semantic_state_items
from app.features.agent_quality.integrations.jev import (
    TypeSafeJevJudge as AppTypeSafeJevJudge,
)
from evaluation.contracts.judges import JudgeDecision as OfflineJudgeDecision
from evaluation.contracts.semantic import semantic_observations as offline_semantic_observations
from evaluation.contracts.semantic_states import (
    SemanticObservations as OfflineSemanticObservations,
)
from evaluation.judges.jev import TypeSafeJevJudge as OfflineTypeSafeJevJudge
from evaluation.rubrics import QUESTIONS as OFFLINE_QUESTIONS
from tests.unit.evaluation.jev_support import FakeTypeSafeClient


def test_offline_runtime_reexports_the_application_contracts_and_rubric() -> None:
    assert OfflineJudgeDecision is AppJudgeDecision
    assert OfflineTypeSafeJevJudge is AppTypeSafeJevJudge
    assert OFFLINE_QUESTIONS is APP_QUESTIONS
    assert OfflineSemanticObservations is SemanticObservations
    assert offline_semantic_observations is app_semantic_observations


def test_semantic_states_are_ordered_projected_and_expand_claims() -> None:
    observations: SemanticObservations = {
        "claim_supported": [
            {"claim": "first", "excerpt": "support one", "citation_ids": ["ev_one"]},
            {"claim": "second", "excerpt": "support two", "citation_ids": ["ev_two"]},
        ],
        "internal_data_leak": {"draft": "draft"},
        "draft_matches_brief": {"brief": "brief", "draft": "draft"},
        "next_step": {"brief": "brief"},
        "entity_resolution_ok": {
            "account_name": "Acme",
            "resolved_profile": "Account name: Acme.",
        },
        "actionability": {"brief": "brief"},
        "tone_fit": None,
    }

    items = semantic_state_items(observations)

    assert [key for key, _state in items] == [
        "claim_supported",
        "claim_supported",
        "internal_data_leak",
        "draft_matches_brief",
        "next_step",
        "entity_resolution_ok",
        "actionability",
    ]
    assert items[0][1] == {"claim": "first", "excerpt": "support one"}


def test_application_runtime_requires_an_explicit_typesafe_credential() -> None:
    with pytest.raises(ValueError, match="TypeSafe API key"):
        AppTypeSafeJevJudge.from_api_key("  ")


def test_application_projection_is_question_specific_and_bounded() -> None:
    assert project_state(
        APP_QUESTIONS["internal_data_leak"],
        {"draft": "synthetic", "raw_prompt": "must not be sent"},
    ) == {"draft": "synthetic"}
    with pytest.raises(ValueError, match="string exceeds"):
        project_state(APP_QUESTIONS["internal_data_leak"], {"draft": "x" * 8_001})


@pytest.mark.asyncio
async def test_application_jev_failure_propagates_without_an_openai_fallback() -> None:
    client = FakeTypeSafeClient([RuntimeError("jev unavailable")])

    with pytest.raises(RuntimeError, match="jev unavailable"):
        await AppTypeSafeJevJudge(client).evaluate("internal_data_leak", {"draft": "synthetic"})

    assert len(client.calls) == 1
    assert "provider" not in client.calls[0]
