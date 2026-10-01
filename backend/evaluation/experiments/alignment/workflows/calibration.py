from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, cast

from evaluation.contracts.judges import SEMANTIC_JUDGE_PROMPT_REVISION, SemanticJudge
from evaluation.experiments.alignment.calibration.policy import (
    AlignmentRecommendation,
    recommend_alignment,
)
from evaluation.experiments.alignment.calibration.results import summarize_attempts
from evaluation.experiments.alignment.calibration.runner import (
    calibration_inputs,
    run_calibration,
)
from evaluation.experiments.alignment.evidence.accepted_sources import (
    ACCEPTED_SOURCE_REVISIONS,
)
from evaluation.experiments.alignment.evidence.trace_models import (
    AlignmentRevisions,
    JudgeTraceIdentity,
    alignment_project_name,
)
from evaluation.experiments.alignment.integrations.langsmith.composite import (
    CompositeClient,
    verify_composite_manifest,
)
from evaluation.experiments.alignment.integrations.langsmith.label_set import (
    LabelSetClientLike,
    publish_approved_label_set,
)
from evaluation.experiments.alignment.integrations.langsmith.phase_manifest import (
    PhaseManifestClient,
    publish_alignment_phase_manifest,
)
from evaluation.experiments.alignment.integrations.langsmith.primary_freeze import (
    verify_primary_freeze,
)
from evaluation.experiments.alignment.integrations.langsmith.publication import LabelingClient
from evaluation.experiments.alignment.integrations.langsmith.tracing import (
    AlignmentTraceClient,
    publish_alignment_attempts,
    verify_alignment_persistence,
)
from evaluation.experiments.alignment.paths import (
    DIAGNOSTIC_REPORT_PATH,
    REPORT_PATH,
    targeted_report_path,
)
from evaluation.experiments.alignment.reference.cases import generate_calibration_cases
from evaluation.experiments.alignment.reference.feedback import (
    FeedbackRecord,
    labels_from_feedback,
    primary_pass_freeze,
)
from evaluation.experiments.alignment.reference.labeling import labeling_run_id
from evaluation.experiments.alignment.reference.labels import validate_calibration_labels
from evaluation.experiments.alignment.reporting.report import write_alignment_report
from evaluation.experiments.alignment.workflows.composite import composite_target
from evaluation.experiments.alignment.workflows.labeling import REVIEWER
from evaluation.experiments.alignment.workflows.support import (
    alignment_code_revision,
    holdout_summary,
)
from evaluation.experiments.hosted.plan import HOSTED_GRAPH_REVISION
from evaluation.judges import JEV_MODEL_VERSION, OPENAI_COMPARISON_MODEL
from evaluation.rubrics import QUESTIONS, RUBRIC_VERSION

CalibrationPhase = Literal["alignment", "holdout"]
EXPECTED_LIVE_CALLS = 420
PHASE_LIVE_CALLS: dict[CalibrationPhase, int] = {"alignment": 210, "holdout": 210}
SCORE_REVISION_QUESTIONS = ("actionability", "tone_fit")
SCORE_REVISION_LIVE_CALLS = 60


async def calibrate_live(
    client: object,
    *,
    judges: dict[str, SemanticJudge],
    label_set: str,
    phase: CalibrationPhase,
    local_only: bool,
    untraced_reason: str | None,
    question_keys: tuple[str, ...] | None = None,
    composite_project: str | None = None,
) -> int:
    if set(judges) != {"jev", "sol"}:
        raise ValueError("calibration requires exactly the jev and sol judges")
    cases = generate_calibration_cases()
    typed_labeling_client = cast("LabelingClient", client)
    typed_composite_client = cast("CompositeClient", client)
    typed_trace_client = cast("AlignmentTraceClient", client)
    typed_manifest_client = cast("PhaseManifestClient", client)
    run_ids = [labeling_run_id(case) for case in cases]
    raw_feedback = tuple(
        typed_labeling_client.list_feedback(
            run_ids=run_ids,
            limit=len(run_ids) * 8 + 1,
        )
    )
    freeze = primary_pass_freeze(
        cases,
        cast("Sequence[FeedbackRecord]", raw_feedback),
        reviewer=REVIEWER,
    )
    verify_primary_freeze(typed_labeling_client, freeze)
    labels = labels_from_feedback(
        cases,
        cast("Sequence[FeedbackRecord]", raw_feedback),
        reviewer=REVIEWER,
        label_set_version=label_set,
        primary_frozen_at=freeze.frozen_at,
    )
    approved = validate_calibration_labels(cases, labels, expected_label_set=label_set)
    publish_approved_label_set(cast("LabelSetClientLike", client), cases, approved)
    first = cases[0]
    revisions = AlignmentRevisions(
        dataset_version=first.dataset_version,
        label_set_version=label_set,
        rubric_version=RUBRIC_VERSION,
        evaluator_version=first.evaluator_version,
        graph_revision=HOSTED_GRAPH_REVISION,
        prompt_revision=SEMANTIC_JUDGE_PROMPT_REVISION,
        code_revision=alignment_code_revision(),
    )
    project_name = alignment_project_name(revisions)
    if phase == "holdout":
        if composite_project is None:
            raise RuntimeError("composite alignment evidence is required before holdout")
        verify_composite_manifest(
            typed_composite_client,
            project_name=composite_project,
            target=composite_target(label_set=label_set),
            cases=cases,
            expected_source_revisions=ACCEPTED_SOURCE_REVISIONS,
        )
    selected_questions = tuple(QUESTIONS) if question_keys is None else question_keys
    if (
        not selected_questions
        or len(set(selected_questions)) != len(selected_questions)
        or any(question_key not in QUESTIONS for question_key in selected_questions)
    ):
        raise ValueError("calibration question scope is invalid")
    if question_keys is not None and phase != "alignment":
        raise ValueError("targeted calibration is supported only for alignment")
    phase_cases = tuple(
        case for case in cases if case.split == phase and case.question_key in selected_questions
    )
    inputs = calibration_inputs(
        phase_cases,
        tuple(
            label for label in approved if label.case_id in {case.case_id for case in phase_cases}
        ),
    )
    attempts = await run_calibration(inputs=inputs, judges=judges)
    expected_calls = len(phase_cases) * 2 * 3
    if len(attempts) != expected_calls:
        raise RuntimeError("live calibration phase coverage is incomplete")
    inventory = {
        (question_key, phase): tuple(
            item.case_id for item in inputs if item.question_key == question_key
        )
        for question_key in selected_questions
    }
    summaries = summarize_attempts(
        attempts,
        expected_case_ids=inventory,  # type: ignore[arg-type]
        judge_keys=("jev", "sol"),
    )
    recommendations: tuple[AlignmentRecommendation, ...] = (
        tuple(
            recommend_alignment(
                jev=holdout_summary(summaries, question_key, "jev"),
                sol=holdout_summary(summaries, question_key, "sol"),
            )
            for question_key in selected_questions
        )
        if phase == "holdout"
        else ()
    )
    published_project: str | None = None
    evidence_complete = False
    if local_only:
        assert untraced_reason is not None
        print(
            "WARNING: alignment tracing skipped by explicit local-only exception; "
            f"reason={untraced_reason}; completed_evidence=false"
        )
    else:
        published_project = project_name
        identities = {
            "jev": JudgeTraceIdentity(model=JEV_MODEL_VERSION, provider="typesafe"),
            "sol": JudgeTraceIdentity(model=OPENAI_COMPARISON_MODEL, provider="openai"),
        }
        publish_alignment_attempts(
            typed_trace_client,
            project_name=project_name,
            attempts=attempts,
            revisions=revisions,
            judges=identities,
        )
        verify_alignment_persistence(
            typed_trace_client,
            project_name=project_name,
            expected_attempts=attempts,
            revisions=revisions,
            judges=identities,
        )
        if phase == "alignment" and question_keys is None:
            publish_alignment_phase_manifest(
                typed_manifest_client,
                project_name=project_name,
                revisions=revisions,
            )
        evidence_complete = phase == "holdout"
    targeted_report = targeted_report_path(SEMANTIC_JUDGE_PROMPT_REVISION)
    report_path = (
        REPORT_PATH
        if phase == "holdout"
        else targeted_report
        if question_keys is not None
        else DIAGNOSTIC_REPORT_PATH
    )
    write_alignment_report(
        report_path,
        summaries=summaries,
        recommendations=recommendations,
        revisions=revisions,
        project_name=published_project,
        evidence_complete=evidence_complete,
        untraced_reason=untraced_reason,
        diagnostic_question_keys=question_keys,
    )
    print(
        "CAM-41/CAM-50 live calibration: PASS; "
        f"phase={phase}; attempts={expected_calls}; "
        f"completed_evidence={str(evidence_complete).lower()}; report={report_path}"
    )
    return 0
