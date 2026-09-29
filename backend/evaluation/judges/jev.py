"""Typed Jev semantic-judge contracts with an injected, offline-testable gateway."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

JEV_MODEL_VERSION = "jev-1.13.0"
QuestionKind = Literal["noul", "choice", "score"]


@dataclass(frozen=True, slots=True)
class JevQuestion:
    key: str
    kind: QuestionKind
    prompt: str
    state_fields: tuple[str, ...]
    options: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CalibrationPlan:
    """Human and repeatability checks required before trusting semantic gates."""

    human_labels_per_question: int
    judge_repetitions: int
    permute_option_order: bool
    minimum_human_agreement: float
    maximum_gap_to_llm_judge: float

    @classmethod
    def default(cls) -> "CalibrationPlan":
        return cls(
            human_labels_per_question=40,
            judge_repetitions=5,
            permute_option_order=True,
            minimum_human_agreement=0.85,
            maximum_gap_to_llm_judge=0.05,
        )


QUESTIONS: Mapping[str, JevQuestion] = {
    "claim_supported": JevQuestion(
        "claim_supported",
        "noul",
        "Is the claim supported by the cited excerpt?",
        ("claim", "excerpt"),
    ),
    "internal_data_leak": JevQuestion(
        "internal_data_leak",
        "noul",
        "Does the draft mention rates, margins, empty capacity, or other customers?",
        ("draft",),
    ),
    "draft_matches_brief": JevQuestion(
        "draft_matches_brief",
        "noul",
        "Does the draft pitch the brief's recommended lanes?",
        ("brief", "draft"),
    ),
    "next_step": JevQuestion(
        "next_step",
        "choice",
        "What is the supported next step?",
        ("brief",),
        ("expand_existing_lanes", "new_lane_pitch", "not_a_fit", "needs_more_data"),
    ),
    "entity_resolution_ok": JevQuestion(
        "entity_resolution_ok",
        "noul",
        "Is the resolved company the same company as the account?",
        ("account_name", "resolved_profile"),
    ),
    "actionability": JevQuestion(
        "actionability",
        "score",
        "How actionable is this brief for a sales rep (1-5)?",
        ("brief",),
        ("1", "2", "3", "4", "5"),
    ),
    "tone_fit": JevQuestion(
        "tone_fit",
        "score",
        "How well does the draft match the rep preferences (1-5)?",
        ("draft", "rep_preferences"),
        ("1", "2", "3", "4", "5"),
    ),
}


class JevGateway(Protocol):
    """Boundary implemented by the TypeSafe SDK only in explicit live runs."""

    def evaluate(
        self, *, model: str, question_key: str, state: dict[str, object], options: tuple[str, ...]
    ) -> dict[str, object]: ...


class JevEvaluator:
    """Projects small trusted state before invoking the decision model."""

    def __init__(self, gateway: JevGateway) -> None:
        self._gateway = gateway

    def evaluate(self, question_key: str, state: Mapping[str, object]) -> dict[str, object]:
        try:
            question = QUESTIONS[question_key]
        except KeyError as error:
            raise ValueError(f"unknown Jev question: {question_key}") from error
        missing = [field for field in question.state_fields if field not in state]
        if missing:
            raise ValueError(f"missing state fields: {', '.join(missing)}")
        projected = {field: state[field] for field in question.state_fields}
        return self._gateway.evaluate(
            model=JEV_MODEL_VERSION,
            question_key=question.key,
            state=projected,
            options=question.options,
        )
