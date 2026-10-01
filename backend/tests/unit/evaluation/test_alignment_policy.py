"""Evidence-only human-alignment recommendation tests."""

from dataclasses import replace

from evaluation.experiments.alignment.calibration.models import QuestionJudgeSummary
from evaluation.experiments.alignment.calibration.policy import recommend_alignment


def _summary(judge: str, agreement: float, coverage: float = 1.0) -> QuestionJudgeSummary:
    return QuestionJudgeSummary(
        question_key="next_step",
        split="holdout",
        judge_key=judge,
        expected_attempts=50,
        valid_attempts=round(50 * coverage),
        unavailable_attempts=50 - round(50 * coverage),
        coverage=coverage,
        exact_agreement=agreement,
        confusion={},
        balanced_accuracy=agreement,
        class_imbalance=False,
        mean_absolute_error=None,
        within_one_agreement=None,
        per_case_disagreement={},
        run_to_run_disagreement=0.0,
        order_sensitivity=0.0,
        order_sensitive_cases=0,
        order_sensitive_eligible_cases=10,
        alternate_order_observations=30,
        alternate_order_expected=30,
        alternate_order_coverage=1.0,
        total_cost_usd=1.0,
        reported_cost_usd=1.0,
        costed_attempts=50,
        cost_unavailable_attempts=0,
        cost_coverage=1.0,
        total_latency_seconds=2.0,
    )


def test_retain_requires_complete_holdout_85_percent_and_within_five_points_of_sol() -> None:
    result = recommend_alignment(jev=_summary("jev", 0.85), sol=_summary("sol", 0.90))
    assert result.recommendation == "retain"
    assert result.evidence_only is True
    assert result.activates_promotion_gate is False


def test_retain_thresholds_fail_immediately_below_either_boundary() -> None:
    below_agreement = recommend_alignment(jev=_summary("jev", 0.8499), sol=_summary("sol", 0.89))
    below_delta = recommend_alignment(jev=_summary("jev", 0.85), sol=_summary("sol", 0.9001))

    assert below_agreement.recommendation == "revise"
    assert below_delta.recommendation == "revise"


def test_incomplete_coverage_can_never_retain() -> None:
    result = recommend_alignment(jev=_summary("jev", 0.99, 0.98), sol=_summary("sol", 0.90))
    assert result.recommendation == "revise"


def test_split_and_post_revision_replace_are_explicit_diagnostic_choices() -> None:
    split = recommend_alignment(
        jev=_summary("jev", 0.70), sol=_summary("sol", 0.90), combined_judgments=True
    )
    replace_result = recommend_alignment(
        jev=_summary("jev", 0.70), sol=_summary("sol", 0.90), revision_attempted=True
    )
    assert split.recommendation == "split"
    assert replace_result.recommendation == "replace"


def test_alignment_slice_cannot_be_recommended_as_holdout() -> None:
    result = recommend_alignment(
        jev=replace(_summary("jev", 0.99), split="alignment"),
        sol=replace(_summary("sol", 0.99), split="alignment"),
    )
    assert result.recommendation == "revise"
