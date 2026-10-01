"""Pure trace identities and sanitized payloads for alignment publication."""

import hashlib
import json
from dataclasses import asdict, dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from evaluation.experiments.alignment.calibration.models import CalibrationAttempt
from evaluation.experiments.alignment.evidence.metadata import (
    ALIGNMENT_PREFIX,
    AlignmentTraceMetadata,
)


@dataclass(frozen=True, slots=True)
class AlignmentRevisions:
    dataset_version: str
    label_set_version: str
    rubric_version: str
    evaluator_version: str
    graph_revision: str
    prompt_revision: str
    code_revision: str

    def __post_init__(self) -> None:
        values = (
            self.dataset_version,
            self.label_set_version,
            self.rubric_version,
            self.evaluator_version,
            self.graph_revision,
            self.prompt_revision,
            self.code_revision,
        )
        if any(not value.strip() for value in values):
            raise ValueError("alignment revisions must be non-empty")


@dataclass(frozen=True, slots=True)
class JudgeTraceIdentity:
    model: str
    provider: str

    def __post_init__(self) -> None:
        if not self.model.strip() or not self.provider.strip():
            raise ValueError("judge trace identity must be non-empty")


@dataclass(frozen=True, slots=True)
class AlignmentPublication:
    project_name: str
    expected_runs: int
    created_runs: int
    created_feedback: int


def alignment_project_name(revisions: AlignmentRevisions) -> str:
    revision_bytes = json.dumps(asdict(revisions), sort_keys=True, separators=(",", ":")).encode()
    revision_hash = hashlib.sha256(revision_bytes).hexdigest()[:16]
    return f"{ALIGNMENT_PREFIX}{revisions.label_set_version}-{revision_hash}"


def alignment_attempt_id(project_name: str, attempt: CalibrationAttempt) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        ":".join(
            (
                project_name,
                attempt.case_id,
                attempt.question_key,
                attempt.judge_key,
                str(attempt.attempt_index),
                attempt.state_hash,
            )
        ),
    )


def trace_metadata(
    attempt: CalibrationAttempt,
    revisions: AlignmentRevisions,
    identity: JudgeTraceIdentity,
) -> dict[str, object]:
    payload = AlignmentTraceMetadata(
        dataset_version=revisions.dataset_version,
        label_set_version=revisions.label_set_version,
        rubric_version=revisions.rubric_version,
        evaluator_version=revisions.evaluator_version,
        graph_revision=revisions.graph_revision,
        prompt_revision=revisions.prompt_revision,
        judge=attempt.judge_key,
        model=identity.model,
        provider=identity.provider,
        code_revision=revisions.code_revision,
        split=attempt.split,
    ).as_dict()
    payload.update(
        {
            "case_id": attempt.case_id,
            "question_key": attempt.question_key,
            "state_hash": attempt.state_hash,
            "attempt_index": attempt.attempt_index,
        }
    )
    return payload


def trace_inputs(attempt: CalibrationAttempt) -> dict[str, object]:
    return {
        "case_id": attempt.case_id,
        "question_key": attempt.question_key,
        "state_hash": attempt.state_hash,
        "split": attempt.split,
        "attempt_index": attempt.attempt_index,
        "option_order": list(attempt.option_order),
    }


def trace_outputs(attempt: CalibrationAttempt) -> dict[str, object]:
    return {
        "status": attempt.status,
        "predicted_value": attempt.predicted_value,
        "latency_seconds": attempt.latency_seconds,
        "estimated_cost_usd": attempt.estimated_cost_usd,
        "error_type": attempt.error_type,
    }
