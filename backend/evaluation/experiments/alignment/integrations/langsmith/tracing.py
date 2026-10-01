"""Sanitized LangSmith publication and readback for real alignment attempts."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from evaluation.experiments.alignment.calibration.metrics import human_agreement
from evaluation.experiments.alignment.calibration.models import CalibrationAttempt
from evaluation.experiments.alignment.evidence.metadata import require_alignment_publication
from evaluation.experiments.alignment.evidence.trace_models import (
    AlignmentPublication,
    AlignmentRevisions,
    JudgeTraceIdentity,
    alignment_attempt_id,
    alignment_project_name,
    trace_inputs,
    trace_metadata,
    trace_outputs,
)
from evaluation.experiments.alignment.integrations.langsmith.trace_queries import (
    AGREEMENT_FEEDBACK_KEY,
    TraceQueryClient,
    existing_ids,
    feedback_rows,
    root_rows,
)


class AlignmentTraceClient(TraceQueryClient, Protocol):
    def create_run(
        self,
        name: str,
        inputs: dict[str, object],
        run_type: str,
        **kwargs: Any,
    ) -> None: ...

    def create_feedback(self, run_id: object, key: str, **kwargs: Any) -> object: ...

    def flush(self, timeout: float | None = None) -> None: ...

    def read_project(self, *, project_name: str) -> object: ...


def publish_alignment_attempts(
    client: AlignmentTraceClient,
    *,
    project_name: str,
    attempts: Sequence[CalibrationAttempt],
    revisions: AlignmentRevisions,
    judges: Mapping[str, JudgeTraceIdentity],
) -> AlignmentPublication:
    """Publish normalized attempts without raw state or provider payloads."""

    if not attempts:
        raise ValueError("alignment publication requires attempts")
    identities: dict[str, JudgeTraceIdentity] = {}
    for attempt in attempts:
        try:
            identities[attempt.judge_key] = judges[attempt.judge_key]
        except KeyError as error:
            raise ValueError(f"judge identity is missing: {attempt.judge_key}") from error
        require_alignment_publication(
            project_name,
            trace_metadata(attempt, revisions, identities[attempt.judge_key]),
        )
    run_ids = [alignment_attempt_id(project_name, attempt) for attempt in attempts]
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("alignment attempts contain duplicate publication identities")
    existing = existing_ids(client, run_ids)
    now = datetime.now(UTC)
    created_runs = 0
    for attempt, run_id in zip(attempts, run_ids, strict=True):
        if str(run_id) in existing:
            continue
        metadata = trace_metadata(attempt, revisions, identities[attempt.judge_key])
        client.create_run(
            f"cam-41-{attempt.judge_key}-{attempt.question_key}",
            trace_inputs(attempt),
            "chain",
            id=run_id,
            project_name=project_name,
            start_time=now,
            end_time=now,
            outputs=trace_outputs(attempt),
            extra={"metadata": metadata},
        )
        created_runs += 1
    client.flush(timeout=60.0)
    project = client.read_project(project_name=project_name)
    session_id = getattr(project, "id", None)
    if not isinstance(session_id, UUID):
        raise RuntimeError("alignment project returned an invalid identifier")
    existing_feedback = {
        (str(getattr(item, "run_id", "")), str(getattr(item, "key", "")))
        for item in feedback_rows(client, run_ids)
    }
    created_feedback = 0
    for attempt, run_id in zip(attempts, run_ids, strict=True):
        identity = (str(run_id), AGREEMENT_FEEDBACK_KEY)
        if identity in existing_feedback:
            continue
        agreement = (
            human_agreement(
                attempt.question_key,
                attempt.predicted_value,
                attempt.human_label,
            )
            if attempt.status == "valid" and attempt.predicted_value is not None
            else None
        )
        client.create_feedback(
            run_id,
            AGREEMENT_FEEDBACK_KEY,
            score=agreement,
            value=attempt.status,
            source_info={"evidence_class": "evaluator_alignment"},
            feedback_id=uuid5(NAMESPACE_URL, f"{run_id}:{AGREEMENT_FEEDBACK_KEY}"),
            trace_id=run_id,
            session_id=session_id,
            start_time=now,
        )
        created_feedback += 1
    client.flush(timeout=60.0)
    return AlignmentPublication(
        project_name=project_name,
        expected_runs=len(attempts),
        created_runs=created_runs,
        created_feedback=created_feedback,
    )


def _root_metadata(run: object) -> Mapping[str, object]:
    extra = getattr(run, "extra", None)
    if not isinstance(extra, Mapping):
        return {}
    metadata = cast("Mapping[str, object]", extra).get("metadata")
    return cast("Mapping[str, object]", metadata) if isinstance(metadata, Mapping) else {}


def verify_alignment_persistence(
    client: AlignmentTraceClient,
    *,
    project_name: str,
    expected_attempts: Sequence[CalibrationAttempt],
    revisions: AlignmentRevisions,
    judges: Mapping[str, JudgeTraceIdentity],
) -> None:
    """Read back exact roots, required metadata, and agreement feedback."""

    client.flush(timeout=60.0)
    run_ids = [alignment_attempt_id(project_name, attempt) for attempt in expected_attempts]
    roots = root_rows(client, project_name, run_ids)
    if len(roots) != len(expected_attempts):
        raise RuntimeError("alignment persistence coverage is incomplete")
    attempts_by_id = {
        str(alignment_attempt_id(project_name, attempt)): attempt for attempt in expected_attempts
    }
    for root in roots:
        run_id = str(getattr(root, "id", ""))
        attempt = attempts_by_id.get(run_id)
        if attempt is None:
            raise RuntimeError("alignment persistence returned an unexpected run")
        try:
            identity = judges[attempt.judge_key]
        except KeyError as error:
            raise RuntimeError("alignment persistence judge identity is missing") from error
        actual = _root_metadata(root)
        expected = trace_metadata(attempt, revisions, identity)
        require_alignment_publication(project_name, actual)
        if any(actual.get(key) != value for key, value in expected.items()):
            raise RuntimeError("alignment persistence metadata is incomplete")
        if getattr(root, "inputs", None) != trace_inputs(attempt):
            raise RuntimeError("alignment persistence inputs drift detected")
        if getattr(root, "outputs", None) != trace_outputs(attempt):
            raise RuntimeError("alignment persistence outputs drift detected")
    feedback = feedback_rows(client, run_ids)
    counts = Counter(
        (str(getattr(item, "run_id", "")), str(getattr(item, "key", ""))) for item in feedback
    )
    expected_counts = Counter((str(run_id), AGREEMENT_FEEDBACK_KEY) for run_id in run_ids)
    if counts != expected_counts:
        raise RuntimeError("alignment persistence feedback coverage is incomplete")
    expected_by_id = {
        str(alignment_attempt_id(project_name, attempt)): attempt for attempt in expected_attempts
    }
    for item in feedback:
        attempt = expected_by_id.get(str(getattr(item, "run_id", "")))
        if attempt is None:
            raise RuntimeError("alignment persistence returned unexpected feedback")
        expected_score = (
            human_agreement(
                attempt.question_key,
                attempt.predicted_value,
                attempt.human_label,
            )
            if attempt.status == "valid" and attempt.predicted_value is not None
            else None
        )
        feedback_source = getattr(item, "feedback_source", None)
        source_info = getattr(feedback_source, "metadata", None)
        typed_source = (
            cast("Mapping[str, object]", source_info) if isinstance(source_info, Mapping) else None
        )
        if (
            getattr(item, "score", None) != expected_score
            or getattr(item, "value", None) != attempt.status
            or typed_source is None
            or typed_source.get("evidence_class") != "evaluator_alignment"
        ):
            raise RuntimeError("alignment persistence feedback drift detected")


__all__ = [
    "AGREEMENT_FEEDBACK_KEY",
    "AlignmentPublication",
    "AlignmentRevisions",
    "JudgeTraceIdentity",
    "alignment_attempt_id",
    "alignment_project_name",
    "publish_alignment_attempts",
    "verify_alignment_persistence",
]
