"""Composite alignment evidence is exact, sanitized, and holdout-bound."""

from __future__ import annotations

from dataclasses import replace

import pytest

from evaluation.experiments.alignment.evidence.composite import (
    CATEGORICAL_QUESTIONS,
    CompositeObservation,
    CompositeTarget,
    compose_alignment_manifest,
    composite_project_name,
)
from evaluation.experiments.alignment.evidence.trace_models import AlignmentRevisions
from evaluation.experiments.alignment.reference.cases import generate_calibration_cases


def _target() -> CompositeTarget:
    return CompositeTarget(
        dataset_version="freight-prospect-v1",
        label_set_version="cam-41-labels-v1",
        rubric_version="semantic-v1",
        evaluator_version="freight-evaluators-v3",
        graph_revision="prospect-intelligence-v1",
        categorical_prompt_revision="shared-question-payload-v2-weighted-scores",
        score_prompt_revision="shared-question-payload-v3-score-anchors",
    )


def _revisions(*, prompt: str, code: str = "abc123") -> AlignmentRevisions:
    target = _target()
    return AlignmentRevisions(
        dataset_version=target.dataset_version,
        label_set_version=target.label_set_version,
        rubric_version=target.rubric_version,
        evaluator_version=target.evaluator_version,
        graph_revision=target.graph_revision,
        prompt_revision=prompt,
        code_revision=code,
    )


def _observations() -> tuple[CompositeObservation, ...]:
    rows: list[CompositeObservation] = []
    for case in generate_calibration_cases():
        if case.split != "alignment":
            continue
        categorical = case.question_key in CATEGORICAL_QUESTIONS
        project = "cam-41-alignment-categorical" if categorical else "cam-41-alignment-score"
        revisions = _revisions(
            prompt=(
                "shared-question-payload-v2-weighted-scores"
                if categorical
                else _target().score_prompt_revision
            )
        )
        for judge in ("jev", "sol"):
            for attempt_index in range(3):
                rows.append(
                    CompositeObservation(
                        project_name=project,
                        case_id=case.case_id,
                        state_hash=case.state_hash,
                        question_key=case.question_key,
                        split="alignment",
                        judge_key=judge,
                        attempt_index=attempt_index,
                        status="valid",
                        revisions=revisions,
                        feedback_verified=True,
                    )
                )
    return tuple(rows)


def _manifest(observations: tuple[CompositeObservation, ...] | None = None):
    return compose_alignment_manifest(
        cases=generate_calibration_cases(),
        observations=_observations() if observations is None else observations,
        target=_target(),
        categorical_project="cam-41-alignment-categorical",
        score_projects=("cam-41-alignment-score",),
    )


def test_composite_contains_exact_sanitized_150_plus_60_inventory() -> None:
    manifest = _manifest()

    assert manifest.logical_attempts == 210
    assert manifest.categorical_attempts == 150
    assert manifest.score_attempts == 60
    assert len(manifest.identity_checksum) == 64
    assert composite_project_name(_target()).startswith("cam-41-alignment-composite-")
    assert sum(source.selected_attempts for source in manifest.sources) == 210
    assert {source.project_name for source in manifest.sources} == {
        "cam-41-alignment-categorical",
        "cam-41-alignment-score",
    }
    serialized = repr(manifest)
    for forbidden in ("human_label", "rationale", "projected_state", "provider_payload"):
        assert forbidden not in serialized


def test_composite_accepts_one_valid_retry_for_an_unavailable_source_attempt() -> None:
    observations = list(_observations())
    original = observations[-1]
    observations[-1] = replace(original, status="unavailable")
    observations.append(
        replace(
            original,
            project_name="cam-41-alignment-score-retry",
            revisions=replace(original.revisions, code_revision="retry456"),
        )
    )

    manifest = compose_alignment_manifest(
        cases=generate_calibration_cases(),
        observations=tuple(observations),
        target=_target(),
        categorical_project="cam-41-alignment-categorical",
        score_projects=("cam-41-alignment-score", "cam-41-alignment-score-retry"),
    )

    assert {source.selected_attempts for source in manifest.sources} >= {1}
    assert sum(source.selected_attempts for source in manifest.sources) == 210


def test_composite_rejects_a_categorical_prompt_revision_mismatch() -> None:
    observations = [
        replace(
            observation,
            revisions=replace(
                observation.revisions, prompt_revision="unexpected-categorical-prompt"
            ),
        )
        if observation.question_key in CATEGORICAL_QUESTIONS
        else observation
        for observation in _observations()
    ]

    with pytest.raises(ValueError, match="revision"):
        _manifest(tuple(observations))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "incomplete"),
        ("duplicate", "overlap"),
        ("holdout", "split"),
        ("bad-revision", "revision"),
        ("bad-judge", "unexpected"),
        ("bad-repetition", "unexpected"),
        ("missing-feedback", "feedback"),
        ("unavailable", "unavailable"),
    ],
)
def test_composite_rejects_incomplete_or_conflicting_evidence(mutation: str, message: str) -> None:
    observations = list(_observations())
    row = observations[-1]
    if mutation == "missing":
        observations.pop()
    elif mutation == "duplicate":
        observations.append(
            replace(row, project_name="cam-41-alignment-score-retry", revisions=row.revisions)
        )
    elif mutation == "holdout":
        observations[-1] = replace(row, split="holdout")
    elif mutation == "bad-revision":
        observations[-1] = replace(
            row, revisions=replace(row.revisions, rubric_version="semantic-v2")
        )
    elif mutation == "bad-judge":
        observations[-1] = replace(row, judge_key="other")
    elif mutation == "bad-repetition":
        observations[-1] = replace(row, attempt_index=3)
    elif mutation == "missing-feedback":
        observations[-1] = replace(row, feedback_verified=False)
    else:
        observations[-1] = replace(row, status="unavailable")

    with pytest.raises((ValueError, RuntimeError), match=message):
        compose_alignment_manifest(
            cases=generate_calibration_cases(),
            observations=tuple(observations),
            target=_target(),
            categorical_project="cam-41-alignment-categorical",
            score_projects=("cam-41-alignment-score", "cam-41-alignment-score-retry"),
        )


def test_composite_project_is_stable_across_source_and_code_revisions() -> None:
    assert composite_project_name(_target()) == composite_project_name(_target())
    assert composite_project_name(_target()) != composite_project_name(
        replace(_target(), score_prompt_revision="shared-question-payload-v2-weighted-scores")
    )
