"""Strict read-back validation for sanitized composite manifests."""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import cast

from evaluation.experiments.alignment.evidence.composite import (
    CATEGORICAL_QUESTIONS,
    COMPOSITE_PREFIX,
    EXPECTED_CATEGORICAL_ATTEMPTS,
    EXPECTED_COMPOSITE_ATTEMPTS,
    EXPECTED_SCORE_ATTEMPTS,
    SCORE_QUESTIONS,
    CompositeTarget,
)
from evaluation.experiments.alignment.evidence.metadata import ALIGNMENT_PREFIX
from evaluation.experiments.alignment.integrations.langsmith.composite_sources import root_metadata


def _source_totals(
    sources: object,
    target: CompositeTarget,
    expected_source_revisions: Mapping[str, str],
) -> tuple[int, Counter[str]]:
    if not isinstance(sources, list) or not sources or not expected_source_revisions:
        raise RuntimeError("composite alignment manifest drift detected")
    question_totals: Counter[str] = Counter()
    selected_total = 0
    seen_projects: set[str] = set()
    revision_names = (
        "dataset_version",
        "label_set_version",
        "rubric_version",
        "evaluator_version",
        "graph_revision",
    )
    for raw in cast("list[object]", sources):
        if not isinstance(raw, Mapping):
            raise RuntimeError("composite alignment manifest drift detected")
        typed_raw = cast("Mapping[str, object]", raw)
        project = typed_raw.get("project_name")
        question_scope = typed_raw.get("question_scope")
        selected = typed_raw.get("selected_attempts")
        question_attempts = typed_raw.get("question_attempts")
        revisions = typed_raw.get("revisions")
        if (
            not isinstance(project, str)
            or not project.startswith(ALIGNMENT_PREFIX)
            or project.startswith(COMPOSITE_PREFIX)
            or project not in expected_source_revisions
            or project in seen_projects
            or not isinstance(selected, int)
            or selected <= 0
            or not isinstance(question_scope, (list, tuple))
            or not isinstance(question_attempts, (list, tuple))
            or not isinstance(revisions, Mapping)
        ):
            raise RuntimeError("composite alignment manifest drift detected")
        seen_projects.add(project)
        typed_scope = cast("Sequence[object]", question_scope)
        if (
            not typed_scope
            or any(
                not isinstance(question, str)
                or question not in (*CATEGORICAL_QUESTIONS, *SCORE_QUESTIONS)
                for question in typed_scope
            )
            or len(set(typed_scope)) != len(typed_scope)
        ):
            raise RuntimeError("composite alignment manifest drift detected")
        typed_attempts = cast("Sequence[object]", question_attempts)
        typed_revisions = cast("Mapping[str, object]", revisions)
        selected_total += selected
        source_count = 0
        for item in typed_attempts:
            if not isinstance(item, (list, tuple)):
                raise RuntimeError("composite alignment manifest drift detected")
            typed_item = cast("Sequence[object]", item)
            if len(typed_item) != 2:
                raise RuntimeError("composite alignment manifest drift detected")
            question, count = typed_item
            if (
                question not in (*CATEGORICAL_QUESTIONS, *SCORE_QUESTIONS)
                or not isinstance(count, int)
                or count <= 0
            ):
                raise RuntimeError("composite alignment manifest drift detected")
            question_totals[cast("str", question)] += count
            source_count += count
        source_questions = {
            cast("str", cast("Sequence[object]", item)[0]) for item in typed_attempts
        }
        if (
            source_count != selected
            or source_questions != set(typed_scope)
            or len(source_questions) != len(typed_attempts)
            or bool(source_questions.intersection(CATEGORICAL_QUESTIONS))
            == bool(source_questions.intersection(SCORE_QUESTIONS))
        ):
            raise RuntimeError("composite alignment manifest drift detected")
        common = all(typed_revisions.get(name) == getattr(target, name) for name in revision_names)
        includes_score = bool(source_questions.intersection(SCORE_QUESTIONS))
        prompt_revision = (
            target.score_prompt_revision if includes_score else target.categorical_prompt_revision
        )
        if (
            not common
            or typed_revisions.get("prompt_revision") != prompt_revision
            or typed_revisions.get("code_revision") != expected_source_revisions[project]
        ):
            raise RuntimeError("composite alignment manifest revision drift detected")
    if seen_projects != set(expected_source_revisions):
        raise RuntimeError("composite alignment manifest source drift detected")
    return selected_total, question_totals


def verify_stored_manifest(
    run: object,
    *,
    target: CompositeTarget,
    expected_checksum: str,
    expected_source_revisions: Mapping[str, str],
) -> None:
    inputs = getattr(run, "inputs", None)
    outputs = getattr(run, "outputs", None)
    metadata = root_metadata(run)
    expected_outputs = {
        "logical_attempts": EXPECTED_COMPOSITE_ATTEMPTS,
        "categorical_attempts": EXPECTED_CATEGORICAL_ATTEMPTS,
        "score_attempts": EXPECTED_SCORE_ATTEMPTS,
        "trace_readback_verified": True,
    }
    if not isinstance(inputs, Mapping):
        raise RuntimeError("composite alignment manifest drift detected")
    typed_inputs = cast("Mapping[str, object]", inputs)
    if (
        getattr(run, "name", None) != "cam-41-composite-manifest"
        or typed_inputs.get("target") != asdict(target)
        or typed_inputs.get("identity_checksum") != expected_checksum
        or outputs != expected_outputs
        or metadata.get("evidence_class") != "evaluator_alignment_composite_manifest"
        or metadata.get("experiment_purpose") != "alignment"
        or metadata.get("alignment_run") is not True
        or metadata.get("record_type") != "composite_completion_manifest"
        or metadata.get("split") != "alignment"
    ):
        raise RuntimeError("composite alignment manifest drift detected")
    selected_total, question_totals = _source_totals(
        typed_inputs.get("sources"), target, expected_source_revisions
    )
    expected_questions = Counter(
        {question: 30 for question in (*CATEGORICAL_QUESTIONS, *SCORE_QUESTIONS)}
    )
    if selected_total != EXPECTED_COMPOSITE_ATTEMPTS or question_totals != expected_questions:
        raise RuntimeError("composite alignment manifest coverage drift detected")


__all__ = ["verify_stored_manifest"]
