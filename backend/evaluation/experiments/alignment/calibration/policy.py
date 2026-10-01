"""Recommendation-only policy for human-preference alignment evidence."""

from dataclasses import dataclass
from typing import Literal

from evaluation.experiments.alignment.calibration.models import QuestionJudgeSummary

RETAIN_AGREEMENT = 0.85
MAX_JEV_DELTA = 0.05
Recommendation = Literal["retain", "revise", "split", "replace"]


@dataclass(frozen=True, slots=True)
class AlignmentRecommendation:
    question_key: str
    recommendation: Recommendation
    reasons: tuple[str, ...]
    jev_agreement_delta_from_sol: float | None
    evidence_only: bool = True
    activates_promotion_gate: bool = False


def recommend_alignment(
    *,
    jev: QuestionJudgeSummary,
    sol: QuestionJudgeSummary,
    combined_judgments: bool = False,
    revision_attempted: bool = False,
) -> AlignmentRecommendation:
    """Interpret holdout evidence without turning semantic thresholds into release gates."""

    if jev.question_key != sol.question_key:
        raise ValueError("alignment summaries must describe the same question")
    agreements_available = jev.exact_agreement is not None and sol.exact_agreement is not None
    delta = (
        jev.exact_agreement - sol.exact_agreement
        if agreements_available
        and jev.exact_agreement is not None
        and sol.exact_agreement is not None
        else None
    )
    complete = jev.coverage == 1.0 and sol.coverage == 1.0
    holdout = jev.split == sol.split == "holdout"
    retains = (
        holdout
        and complete
        and jev.exact_agreement is not None
        and jev.exact_agreement >= RETAIN_AGREEMENT
        and delta is not None
        and delta >= -MAX_JEV_DELTA - 1e-12
    )
    if retains:
        recommendation: Recommendation = "retain"
        reasons = ("complete holdout evidence meets the documented recommendation thresholds",)
    elif combined_judgments:
        recommendation = "split"
        reasons = ("the rubric combines separable human judgments",)
    elif revision_attempted and delta is not None and delta < -MAX_JEV_DELTA - 1e-12:
        recommendation = "replace"
        reasons = ("the comparison judge remains materially better after bounded revision",)
    else:
        recommendation = "revise"
        reasons_list: list[str] = []
        if not holdout:
            reasons_list.append("retain decisions require an untouched holdout slice")
        if not complete:
            reasons_list.append("attempt coverage is incomplete")
        if jev.exact_agreement is None or jev.exact_agreement < RETAIN_AGREEMENT:
            reasons_list.append("Jev agreement is below the documented threshold")
        if delta is not None and delta < -MAX_JEV_DELTA - 1e-12:
            reasons_list.append("Jev trails the comparison judge by more than five points")
        reasons = tuple(reasons_list) or ("rubric or projection needs diagnosis",)
    return AlignmentRecommendation(
        question_key=jev.question_key,
        recommendation=recommendation,
        reasons=reasons,
        jev_agreement_delta_from_sol=delta,
    )
