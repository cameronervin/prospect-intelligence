"""Alignment reports retain aggregate evidence and omit sensitive row data."""

from pathlib import Path

import pytest

from evaluation.experiments.alignment.calibration.models import QuestionJudgeSummary
from evaluation.experiments.alignment.calibration.policy import AlignmentRecommendation
from evaluation.experiments.alignment.evidence.trace_models import AlignmentRevisions
from evaluation.experiments.alignment.reporting.report import write_alignment_report
from evaluation.rubrics import QUESTIONS


def _summary(
    *, split: str, judge: str, question: str = "internal_data_leak"
) -> QuestionJudgeSummary:
    return QuestionJudgeSummary(
        question_key=question,
        split=split,  # type: ignore[arg-type]
        judge_key=judge,
        expected_attempts=50,
        valid_attempts=50,
        unavailable_attempts=0,
        coverage=1.0,
        exact_agreement=0.9,
        confusion=(
            {"false": {"false": 20, "true": 5}, "true": {"false": 0, "true": 25}}
            if question == "internal_data_leak"
            else {}
        ),
        balanced_accuracy=0.9,
        class_imbalance=False,
        mean_absolute_error=None,
        within_one_agreement=None,
        per_case_disagreement={"SECRET-CASE-ID": 0.2},
        run_to_run_disagreement=0.1,
        order_sensitivity=0.0,
        order_sensitive_cases=0,
        order_sensitive_eligible_cases=0,
        alternate_order_observations=0,
        alternate_order_expected=0,
        alternate_order_coverage=None,
        total_cost_usd=0.25,
        reported_cost_usd=0.25,
        costed_attempts=50,
        cost_unavailable_attempts=0,
        cost_coverage=1.0,
        total_latency_seconds=5.0,
    )


def _revisions() -> AlignmentRevisions:
    return AlignmentRevisions(
        dataset_version="freight-prospect-v1",
        label_set_version="cam-41-labels-v1",
        rubric_version="semantic-v1",
        evaluator_version="freight-evaluators-v3",
        graph_revision="prospect-intelligence-v1",
        prompt_revision="v1",
        code_revision="abc123",
    )


def _recommendation(question: str = "internal_data_leak") -> AlignmentRecommendation:
    return AlignmentRecommendation(
        question_key=question,
        recommendation="retain",
        reasons=("PRIVATE-PROVIDER-PAYLOAD",),
        jev_agreement_delta_from_sol=-0.02,
    )


def _complete_summaries() -> tuple[QuestionJudgeSummary, ...]:
    return tuple(
        _summary(split="holdout", judge=judge, question=question)
        for question in QUESTIONS
        for judge in ("jev", "sol")
    )


def _complete_recommendations() -> tuple[AlignmentRecommendation, ...]:
    return tuple(_recommendation(question) for question in QUESTIONS)


def test_complete_report_contains_only_sanitized_aggregates(tmp_path: Path) -> None:
    destination = tmp_path / "reports" / "alignment.md"

    written = write_alignment_report(
        destination,
        summaries=_complete_summaries(),
        recommendations=_complete_recommendations(),
        revisions=_revisions(),
        project_name="cam-41-alignment-labels-v1-abc123",
        evidence_complete=True,
    )

    report = written.read_text()
    assert written == destination
    assert "COMPLETE — LangSmith read-back verified" in report
    assert "cam-41-alignment-labels-v1-abc123" in report
    assert "freight-prospect-v1" in report and "abc123" in report
    assert "internal_data_leak" in report
    assert "90.00%" in report and "retain" in report
    assert "false→true=5" in report
    for forbidden in (
        "SECRET-CASE-ID",
        "PRIVATE-PROVIDER-PAYLOAD",
        "projected_state",
        "RAW-PROVIDER-PAYLOAD",
    ):
        assert forbidden not in report


def test_local_only_report_is_explicitly_incomplete(tmp_path: Path) -> None:
    path = write_alignment_report(
        tmp_path / "local.md",
        summaries=(_summary(split="holdout", judge="jev"),),
        recommendations=(_recommendation(),),
        revisions=_revisions(),
        project_name=None,
        evidence_complete=False,
        untraced_reason="Explicit diagnostic after a tracing outage.",
    )

    report = path.read_text()
    assert "INCOMPLETE — local-only/untraced" in report
    assert "Explicit diagnostic after a tracing outage." in report
    assert "cannot satisfy completed alignment evidence" in report


def test_traced_alignment_phase_is_diagnostic_not_completed_holdout(tmp_path: Path) -> None:
    path = write_alignment_report(
        tmp_path / "diagnostic.md",
        summaries=tuple(
            _summary(split="alignment", judge=judge, question=question)
            for question in QUESTIONS
            for judge in ("jev", "sol")
        ),
        recommendations=(),
        revisions=_revisions(),
        project_name="cam-41-alignment-diagnostic",
        evidence_complete=False,
    )

    assert "DIAGNOSTIC COMPLETE" in path.read_text()

    partial = write_alignment_report(
        tmp_path / "partial-diagnostic.md",
        summaries=(_summary(split="alignment", judge="jev"),),
        recommendations=(),
        revisions=_revisions(),
        project_name="cam-41-alignment-partial-diagnostic",
        evidence_complete=False,
    )
    assert "DIAGNOSTIC COMPLETE" not in partial.read_text()


def test_explicit_targeted_diagnostic_is_readback_complete_for_its_scope(tmp_path: Path) -> None:
    path = write_alignment_report(
        tmp_path / "score-diagnostic.md",
        summaries=tuple(
            _summary(split="alignment", judge=judge, question=question)
            for question in ("actionability", "tone_fit")
            for judge in ("jev", "sol")
        ),
        recommendations=(),
        revisions=_revisions(),
        project_name="cam-41-alignment-score-revision",
        evidence_complete=False,
        diagnostic_question_keys=("actionability", "tone_fit"),
        supporting_project_names=("cam-41-alignment-score-retry",),
    )

    report = path.read_text()
    assert "TARGETED DIAGNOSTIC COMPLETE" in report
    assert "`actionability`, `tone_fit`" in report
    assert "cam-41-alignment-score-retry" in report


def test_report_rejects_inconsistent_completion_and_unsafe_aggregates(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="project name"):
        write_alignment_report(
            tmp_path / "bad.md",
            summaries=_complete_summaries(),
            recommendations=_complete_recommendations(),
            revisions=_revisions(),
            project_name=None,
            evidence_complete=True,
        )

    with pytest.raises(ValueError, match="exact holdout coverage"):
        write_alignment_report(
            tmp_path / "partial.md",
            summaries=(
                _summary(split="holdout", judge="jev"),
                _summary(split="holdout", judge="sol"),
            ),
            recommendations=(_recommendation(),),
            revisions=_revisions(),
            project_name="cam-41-alignment-partial",
            evidence_complete=True,
        )

    bad = _summary(split="holdout", judge="jev")
    object.__setattr__(bad, "confusion", {"PRIVATE-PAYLOAD": {"true": 1}})
    with pytest.raises(ValueError, match="confusion"):
        write_alignment_report(
            tmp_path / "unsafe.md",
            summaries=(bad,),
            recommendations=(_recommendation(),),
            revisions=_revisions(),
            project_name=None,
            evidence_complete=False,
        )
