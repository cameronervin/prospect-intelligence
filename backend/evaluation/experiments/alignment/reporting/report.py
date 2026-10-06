"""Sanitized aggregate Markdown for CAM-41/CAM-50 alignment evidence."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

from evaluation.experiments.alignment.calibration.models import QuestionJudgeSummary
from evaluation.experiments.alignment.calibration.policy import AlignmentRecommendation
from evaluation.experiments.alignment.evidence.metadata import ALIGNMENT_PREFIX
from evaluation.experiments.alignment.evidence.trace_models import AlignmentRevisions
from evaluation.experiments.alignment.reporting.report_tables import (
    confusion_text,
    metric_lines,
    percent,
)
from evaluation.experiments.alignment.reporting.report_validation import (
    safe_text,
    validate_summary,
)
from evaluation.rubrics import QUESTIONS


def _render_alignment_report(
    *,
    summaries: Sequence[QuestionJudgeSummary],
    recommendations: Sequence[AlignmentRecommendation],
    revisions: AlignmentRevisions,
    project_name: str | None,
    evidence_complete: bool,
    untraced_reason: str | None,
    diagnostic_question_keys: Sequence[str] | None,
    supporting_project_names: Sequence[str],
) -> str:
    if not summaries:
        raise ValueError("alignment report requires aggregate summaries")
    identities = [(summary.question_key, summary.split, summary.judge_key) for summary in summaries]
    if len(set(identities)) != len(identities):
        raise ValueError("alignment report contains duplicate aggregate summaries")
    for summary in summaries:
        validate_summary(summary)

    decisions = {item.question_key: item for item in recommendations}
    if len(decisions) != len(recommendations) or any(key not in QUESTIONS for key in decisions):
        raise ValueError("alignment report recommendations are invalid")
    for recommendation in recommendations:
        if recommendation.activates_promotion_gate or not recommendation.evidence_only:
            raise ValueError("alignment recommendations must remain evidence-only")
        if recommendation.recommendation not in {"retain", "revise", "split", "replace"}:
            raise ValueError("alignment report recommendation is invalid")
        delta = recommendation.jev_agreement_delta_from_sol
        if delta is not None and (not math.isfinite(delta) or not -1.0 <= delta <= 1.0):
            raise ValueError("alignment report recommendation delta is invalid")
    if evidence_complete:
        expected_identities = {
            (question_key, "holdout", judge_key)
            for question_key in QUESTIONS
            for judge_key in ("jev", "sol")
        }
        if set(identities) != expected_identities or set(decisions) != set(QUESTIONS):
            raise ValueError("completed alignment report requires exact holdout coverage")
    diagnostic_scope = tuple(diagnostic_question_keys or ())
    if diagnostic_scope and (
        evidence_complete
        or len(set(diagnostic_scope)) != len(diagnostic_scope)
        or any(question not in QUESTIONS for question in diagnostic_scope)
        or set(identities)
        != {
            (question_key, "alignment", judge_key)
            for question_key in diagnostic_scope
            for judge_key in ("jev", "sol")
        }
        or recommendations
    ):
        raise ValueError("targeted diagnostic scope does not match its aggregate summaries")

    revision_values = {
        "Dataset": revisions.dataset_version,
        "Label set": revisions.label_set_version,
        "Rubric": revisions.rubric_version,
        "Evaluator": revisions.evaluator_version,
        "Graph": revisions.graph_revision,
        "Prompt": revisions.prompt_revision,
        "Code": revisions.code_revision,
    }
    safe_revisions = {
        key: safe_text(value, name=f"{key.lower()} revision")
        for key, value in revision_values.items()
    }
    safe_project = (
        safe_text(project_name, name="alignment project name") if project_name is not None else None
    )
    safe_supporting_projects = tuple(
        safe_text(project, name="supporting alignment project name")
        for project in supporting_project_names
    )
    if (
        len(set(safe_supporting_projects)) != len(safe_supporting_projects)
        or any(not project.startswith(ALIGNMENT_PREFIX) for project in safe_supporting_projects)
        or safe_project in safe_supporting_projects
    ):
        raise ValueError("supporting alignment project names are invalid")
    safe_reason = (
        safe_text(untraced_reason, name="untraced reason") if untraced_reason is not None else None
    )
    if evidence_complete:
        if safe_project is None or not safe_project.startswith(ALIGNMENT_PREFIX):
            raise ValueError("completed alignment evidence requires its project name")
        if safe_reason is not None:
            raise ValueError("completed alignment evidence cannot have an untraced reason")
        status = "COMPLETE — LangSmith read-back verified"
    elif safe_reason is not None:
        status = "INCOMPLETE — local-only/untraced"
    elif (
        diagnostic_scope and safe_project is not None and safe_project.startswith(ALIGNMENT_PREFIX)
    ):
        status = "TARGETED DIAGNOSTIC COMPLETE — read-back verified; holdout not run"
    elif (
        safe_project is not None
        and safe_project.startswith(ALIGNMENT_PREFIX)
        and set(identities)
        == {
            (question_key, "alignment", judge_key)
            for question_key in QUESTIONS
            for judge_key in ("jev", "sol")
        }
        and not recommendations
    ):
        status = "DIAGNOSTIC COMPLETE — read-back verified; holdout not run"
    else:
        status = "INCOMPLETE — LangSmith read-back not verified"

    lines = [
        "# CAM-41/CAM-50 Human-Preference Alignment Report",
        "",
        "This report contains sanitized aggregate alignment evidence only. It excludes case IDs, "
        "projected state, prompts, traces, and provider payloads.",
        "",
        "## Evidence status",
        "",
        f"- Status: **{status}**",
        (
            f"- LangSmith project: `{safe_project}`"
            if safe_project is not None
            else "- LangSmith project: not published"
        ),
    ]
    if safe_reason is not None:
        lines.extend(
            [
                f"- Untraced reason: {safe_reason}",
                "- This local-only run cannot satisfy completed alignment evidence.",
            ]
        )
    if diagnostic_scope:
        lines.append(
            "- Targeted questions: "
            + ", ".join(f"`{question_key}`" for question_key in diagnostic_scope)
        )
    if safe_supporting_projects:
        lines.append(
            "- Supporting LangSmith projects: "
            + ", ".join(f"`{project}`" for project in safe_supporting_projects)
        )
    lines.extend(["", "## Revisions", ""])
    lines.extend(f"- {name}: `{value}`" for name, value in safe_revisions.items())
    lines.extend(["", "## Per-question judge metrics", "", *metric_lines(summaries)])
    lines.extend(
        [
            "",
            "## Aggregate confusion counts",
            "",
            "| Question | Split | Judge | Counts (human→judge) |",
            "| --- | --- | --- | --- |",
        ]
    )
    lines.extend(
        f"| `{summary.question_key}` | `{summary.split}` | `{summary.judge_key}` | "
        f"{confusion_text(summary)} |"
        for summary in summaries
    )
    lines.extend(["", "## Per-question recommendations", ""])
    if recommendations:
        lines.extend(
            [
                "| Question | Recommendation | Jev agreement delta from Sol | Release gate |",
                "| --- | --- | ---: | --- |",
            ]
        )
        lines.extend(
            f"| `{item.question_key}` | `{item.recommendation}` | "
            f"{percent(item.jev_agreement_delta_from_sol)} | no; evidence only |"
            for item in recommendations
        )
    elif all(summary.split == "alignment" for summary in summaries):
        lines.append("No recommendations: the untouched holdout was not run.")
    else:
        lines.append("No recommendations: this evidence set is incomplete.")
    lines.extend(
        [
            "",
            "Semantic diagnostics remain evidence only; deterministic release gates are unchanged.",
            "",
        ]
    )
    return "\n".join(lines)


def write_alignment_report(
    path: Path,
    *,
    summaries: Sequence[QuestionJudgeSummary],
    recommendations: Sequence[AlignmentRecommendation],
    revisions: AlignmentRevisions,
    project_name: str | None,
    evidence_complete: bool,
    untraced_reason: str | None = None,
    diagnostic_question_keys: Sequence[str] | None = None,
    supporting_project_names: Sequence[str] = (),
) -> Path:
    """Write only sanitized aggregates and return the report path."""

    report = _render_alignment_report(
        summaries=summaries,
        recommendations=recommendations,
        revisions=revisions,
        project_name=project_name,
        evidence_complete=evidence_complete,
        untraced_reason=untraced_reason,
        diagnostic_question_keys=diagnostic_question_keys,
        supporting_project_names=supporting_project_names,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report)
    return path


__all__ = ["write_alignment_report"]
