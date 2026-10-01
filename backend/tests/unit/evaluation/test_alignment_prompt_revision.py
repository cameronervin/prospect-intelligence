"""The single bounded score-prompt experiment has a reproducible decision rule."""

import math
from dataclasses import replace

import pytest

from evaluation.experiments.alignment.calibration.prompt_revision import (
    SCORE_PROMPT_CANDIDATE_GUIDANCE,
    SCORE_PROMPT_CANDIDATE_REVISION,
    ScorePromptMetrics,
    decide_score_prompt_revision,
)


def _metrics(
    *,
    exact: float,
    mae: float,
    within_one: float,
    disagreement: float = 0.0,
    order_sensitivity: float = 0.0,
) -> ScorePromptMetrics:
    return ScorePromptMetrics(
        coverage=1.0,
        exact_agreement=exact,
        mean_absolute_error=mae,
        within_one_agreement=within_one,
        run_to_run_disagreement=disagreement,
        order_sensitivity=order_sensitivity,
    )


def test_recorded_v3_candidate_is_rejected_by_the_frozen_rule() -> None:
    baseline = {
        "actionability": _metrics(exact=0.60, mae=0.565, within_one=0.80),
        "tone_fit": _metrics(exact=0.60, mae=0.442, within_one=0.8667),
    }
    candidate = {
        "actionability": _metrics(
            exact=0.6667,
            mae=0.483,
            within_one=0.80,
            disagreement=0.0667,
            order_sensitivity=0.20,
        ),
        "tone_fit": _metrics(exact=0.60, mae=0.464, within_one=0.80),
    }

    decision = decide_score_prompt_revision(baseline=baseline, candidate=candidate)

    assert decision.accepted is False
    assert "within-one regression" in decision.reasons
    assert "instability regression" in decision.reasons
    assert SCORE_PROMPT_CANDIDATE_REVISION == "shared-question-payload-v3-score-anchors"
    assert "closest stated anchor" in SCORE_PROMPT_CANDIDATE_GUIDANCE


def test_candidate_is_accepted_only_for_complete_stable_non_regressing_improvement() -> None:
    baseline = {
        "actionability": _metrics(exact=0.60, mae=0.50, within_one=0.80),
        "tone_fit": _metrics(exact=0.60, mae=0.40, within_one=0.80),
    }
    candidate = {
        "actionability": _metrics(exact=0.70, mae=0.40, within_one=0.90),
        "tone_fit": _metrics(exact=0.60, mae=0.35, within_one=0.80),
    }

    assert decide_score_prompt_revision(baseline=baseline, candidate=candidate).accepted is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("coverage", math.nan),
        ("exact_agreement", 1.1),
        ("mean_absolute_error", -0.1),
        ("within_one_agreement", math.inf),
        ("run_to_run_disagreement", -0.1),
        ("order_sensitivity", 1.1),
    ],
)
def test_prompt_comparison_rejects_non_finite_or_out_of_range_metrics(
    field: str, value: float
) -> None:
    baseline = _metrics(exact=0.60, mae=0.50, within_one=0.80)

    with pytest.raises(ValueError, match="score-prompt metric"):
        replace(baseline, **{field: value})
