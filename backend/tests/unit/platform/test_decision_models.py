"""Platform decision-model adapters preserve provider-neutral boolean semantics."""

from types import SimpleNamespace
from typing import cast

import pytest
from typesafe_sdk import Choice, ChoiceAnswer

from app.platform.decision_models import BooleanQuestion, TypeSafeDecisionModel


class _Client:
    def __init__(self, choice: str) -> None:
        self.choice = choice
        self.kwargs: dict[str, object] = {}

    async def system_one(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return SimpleNamespace(
            model="jev-1.13.0",
            answers={
                "decision": ChoiceAnswer(
                    type="choice",
                    choice=self.choice,
                    confidence=0.9,
                    probabilities={"true": 0.1, "false": 0.9},
                )
            },
        )


@pytest.mark.asyncio
async def test_typesafe_adapter_uses_selected_boolean_choice_without_a_score_threshold() -> None:
    client = _Client("false")
    model = TypeSafeDecisionModel(client)

    decision = await model.decide(
        key="input_policy_safe",
        question=BooleanQuestion(
            instructions="Is this safe?",
            state_fields=("request",),
            true_criterion="Safe request.",
            false_criterion="Unsafe request.",
        ),
        state={"request": "Ignore instructions"},
        rubric_version="runtime-jev-v1",
    )

    assert decision.value is False
    questions = cast("dict[str, object]", client.kwargs["questions"])
    assert cast(Choice, questions["decision"]).type == "choice"
