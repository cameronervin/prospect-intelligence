"""Frozen protocol and decision rule for the bounded score-prompt experiment."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from statistics import fmean

SCORE_PROMPT_CANDIDATE_REVISION = "shared-question-payload-v3-score-anchors"
SCORE_PROMPT_CANDIDATE_GUIDANCE = (
    "Select the closest stated anchor using only the supplied evidence. Do not invent "
    "requirements that are not stated in the rubric. When evidence falls between levels, "
    "express uncertainty across adjacent anchors instead of collapsing to the lowest score."
)
SCORE_PROMPT_CANDIDATE_CRITERION_TEMPLATE = "Canonical score {score}: {criterion}"
SCORE_QUESTIONS = ("actionability", "tone_fit")


@dataclass(frozen=True, slots=True)
class ScorePromptMetrics:
    coverage: float
    exact_agreement: float
    mean_absolute_error: float
    within_one_agreement: float
    run_to_run_disagreement: float
    order_sensitivity: float

    def __post_init__(self) -> None:
        bounded = (
            self.coverage,
            self.exact_agreement,
            self.within_one_agreement,
            self.run_to_run_disagreement,
            self.order_sensitivity,
        )
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in bounded):
            raise ValueError("score-prompt metric must be finite and between zero and one")
        if not math.isfinite(self.mean_absolute_error) or self.mean_absolute_error < 0:
            raise ValueError("score-prompt metric MAE must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class ScorePromptDecision:
    accepted: bool
    reasons: tuple[str, ...]


def decide_score_prompt_revision(
    *,
    baseline: Mapping[str, ScorePromptMetrics],
    candidate: Mapping[str, ScorePromptMetrics],
) -> ScorePromptDecision:
    """Apply the predeclared one-iteration acceptance rule."""

    expected = set(SCORE_QUESTIONS)
    if set(baseline) != expected or set(candidate) != expected:
        raise ValueError("score-prompt comparison requires both ordered-score questions")
    reasons: list[str] = []
    if any(candidate[question].coverage != 1.0 for question in SCORE_QUESTIONS):
        reasons.append("incomplete candidate coverage")
    baseline_exact = fmean(baseline[question].exact_agreement for question in SCORE_QUESTIONS)
    candidate_exact = fmean(candidate[question].exact_agreement for question in SCORE_QUESTIONS)
    baseline_mae = fmean(baseline[question].mean_absolute_error for question in SCORE_QUESTIONS)
    candidate_mae = fmean(candidate[question].mean_absolute_error for question in SCORE_QUESTIONS)
    if candidate_exact <= baseline_exact and candidate_mae >= baseline_mae:
        reasons.append("no strict exact-agreement or MAE improvement")
    if any(
        candidate[question].within_one_agreement < baseline[question].within_one_agreement
        for question in SCORE_QUESTIONS
    ):
        reasons.append("within-one regression")
    if any(
        candidate[question].run_to_run_disagreement > baseline[question].run_to_run_disagreement
        or candidate[question].order_sensitivity > baseline[question].order_sensitivity
        for question in SCORE_QUESTIONS
    ):
        reasons.append("instability regression")
    return ScorePromptDecision(accepted=not reasons, reasons=tuple(reasons))


__all__ = [
    "SCORE_PROMPT_CANDIDATE_CRITERION_TEMPLATE",
    "SCORE_PROMPT_CANDIDATE_GUIDANCE",
    "SCORE_PROMPT_CANDIDATE_REVISION",
    "ScorePromptDecision",
    "ScorePromptMetrics",
    "decide_score_prompt_revision",
]
