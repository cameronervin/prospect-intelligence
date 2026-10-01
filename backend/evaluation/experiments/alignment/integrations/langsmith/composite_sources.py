"""Read exact alignment attempts and feedback from explicit LangSmith projects."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from evaluation.experiments.alignment.contracts import CalibrationCase
from evaluation.experiments.alignment.evidence.composite import (
    CATEGORICAL_QUESTIONS,
    SCORE_QUESTIONS,
    CompositeManifest,
    CompositeObservation,
    CompositeTarget,
    compose_alignment_manifest,
)
from evaluation.experiments.alignment.evidence.metadata import require_alignment_publication
from evaluation.experiments.alignment.evidence.trace_models import AlignmentRevisions
from evaluation.experiments.alignment.integrations.langsmith.trace_queries import (
    AGREEMENT_FEEDBACK_KEY,
    feedback_rows,
    root_rows,
)


class CompositeClient(Protocol):
    def list_runs(self, **kwargs: Any) -> Iterator[object]: ...
    def list_feedback(self, **kwargs: Any) -> Iterator[object]: ...
    def create_run(
        self, name: str, inputs: dict[str, object], run_type: str, **kwargs: Any
    ) -> None: ...
    def flush(self, timeout: float | None = None) -> None: ...


def source_attempt_id(
    project_name: str, case: CalibrationCase, judge_key: str, attempt_index: int
) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        ":".join(
            (
                project_name,
                case.case_id,
                case.question_key,
                judge_key,
                str(attempt_index),
                case.state_hash,
            )
        ),
    )


def root_metadata(run: object) -> Mapping[str, object]:
    extra = getattr(run, "extra", None)
    metadata = (
        cast("Mapping[str, object]", extra).get("metadata") if isinstance(extra, Mapping) else None
    )
    return cast("Mapping[str, object]", metadata) if isinstance(metadata, Mapping) else {}


def _revisions(metadata: Mapping[str, object]) -> AlignmentRevisions:
    names = (
        "dataset_version",
        "label_set_version",
        "rubric_version",
        "evaluator_version",
        "graph_revision",
        "prompt_revision",
        "code_revision",
    )
    values = {name: metadata.get(name) for name in names}
    if any(not isinstance(value, str) for value in values.values()):
        raise RuntimeError("composite source revision metadata is incomplete")
    return AlignmentRevisions(**cast("dict[str, str]", values))


def _feedback_verified(item: object, status: str) -> bool:
    source = getattr(item, "feedback_source", None)
    source_metadata = getattr(source, "metadata", None)
    typed_metadata = (
        cast("Mapping[str, object]", source_metadata)
        if isinstance(source_metadata, Mapping)
        else None
    )
    return bool(
        getattr(item, "key", None) == AGREEMENT_FEEDBACK_KEY
        and getattr(item, "value", None) == status
        and typed_metadata is not None
        and typed_metadata.get("evidence_class") == "evaluator_alignment"
    )


def _read_project_observations(
    client: CompositeClient,
    *,
    project_name: str,
    cases: Sequence[CalibrationCase],
) -> tuple[CompositeObservation, ...]:
    requested = [
        source_attempt_id(project_name, case, judge, repetition)
        for case in cases
        for judge in ("jev", "sol")
        for repetition in range(3)
    ]
    roots = root_rows(client, project_name, requested)
    root_counts = Counter(str(getattr(root, "id", "")) for root in roots)
    if any(count != 1 for count in root_counts.values()):
        raise RuntimeError("composite source returned duplicate roots")
    feedback = feedback_rows(client, [cast("UUID", root.id) for root in roots])  # type: ignore[attr-defined]
    feedback_by_run: dict[str, list[object]] = {}
    for item in feedback:
        feedback_by_run.setdefault(str(getattr(item, "run_id", "")), []).append(item)
    observations: list[CompositeObservation] = []
    case_by_id = {case.case_id: case for case in cases}
    for root in roots:
        inputs = getattr(root, "inputs", None)
        outputs = getattr(root, "outputs", None)
        metadata = root_metadata(root)
        try:
            require_alignment_publication(project_name, metadata)
        except ValueError as error:
            raise RuntimeError("composite source metadata is incomplete") from error
        if not isinstance(inputs, Mapping) or not isinstance(outputs, Mapping):
            raise RuntimeError("composite source payload is incomplete")
        typed_inputs = cast("Mapping[str, object]", inputs)
        typed_outputs = cast("Mapping[str, object]", outputs)
        case_id = typed_inputs.get("case_id")
        question = typed_inputs.get("question_key")
        state_hash = typed_inputs.get("state_hash")
        split = typed_inputs.get("split")
        repetition = typed_inputs.get("attempt_index")
        judge = metadata.get("judge")
        status = typed_outputs.get("status")
        if not (
            isinstance(case_id, str)
            and isinstance(question, str)
            and isinstance(state_hash, str)
            and isinstance(split, str)
            and isinstance(repetition, int)
            and isinstance(judge, str)
            and isinstance(status, str)
        ):
            raise RuntimeError("composite source identity is incomplete")
        case = case_by_id.get(case_id)
        if case is None or str(getattr(root, "id", "")) != str(
            source_attempt_id(project_name, case, judge, repetition)
        ):
            raise RuntimeError("composite source identity drift detected")
        expected_fields = {
            "case_id": case_id,
            "question_key": question,
            "state_hash": state_hash,
            "split": split,
            "attempt_index": repetition,
        }
        if any(metadata.get(key) != value for key, value in expected_fields.items()):
            raise RuntimeError("composite source metadata drift detected")
        rows = feedback_by_run.get(str(getattr(root, "id", "")), [])
        observations.append(
            CompositeObservation(
                project_name=project_name,
                case_id=case_id,
                state_hash=state_hash,
                question_key=question,
                split=split,
                judge_key=judge,
                attempt_index=repetition,
                status=status,
                revisions=_revisions(metadata),
                feedback_verified=len(rows) == 1 and _feedback_verified(rows[0], status),
            )
        )
    return tuple(observations)


def build_composite_from_langsmith(
    client: CompositeClient,
    *,
    cases: Sequence[CalibrationCase],
    target: CompositeTarget,
    categorical_project: str,
    score_projects: Sequence[str],
) -> CompositeManifest:
    alignment = tuple(case for case in cases if case.split == "alignment")
    category_cases = tuple(case for case in alignment if case.question_key in CATEGORICAL_QUESTIONS)
    score_cases = tuple(case for case in alignment if case.question_key in SCORE_QUESTIONS)
    observations = list(
        _read_project_observations(client, project_name=categorical_project, cases=category_cases)
    )
    for project in score_projects:
        observations.extend(
            _read_project_observations(client, project_name=project, cases=score_cases)
        )
    return compose_alignment_manifest(
        cases=cases,
        observations=observations,
        target=target,
        categorical_project=categorical_project,
        score_projects=score_projects,
    )


__all__ = [
    "CompositeClient",
    "build_composite_from_langsmith",
    "root_metadata",
    "source_attempt_id",
]
