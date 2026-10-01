"""Record/domain mapping for PostgreSQL regression persistence."""

from collections.abc import Mapping
from typing import Any, cast

from app.features.agent_quality.domain.regression import (
    AuditAction,
    CandidateSource,
    CandidateStatus,
    PromotedRegressionExample,
    RegressionAuditEntry,
    RegressionCandidate,
)
from app.features.agent_quality.models import (
    RegressionAuditRecord,
    RegressionCandidateRecord,
    RegressionExampleRecord,
)


def candidate_values(candidate: RegressionCandidate) -> dict[str, object]:
    return {
        "candidate_id": candidate.candidate_id,
        "source_kind": candidate.source_kind.value,
        "source_run_id": candidate.source_run_id,
        "source_event_id": candidate.source_event_id,
        "failure_type": candidate.failure_type,
        "sanitized_input": dict(candidate.sanitized_input),
        "sanitized_reference": dict(candidate.sanitized_reference),
        "evidence": dict(candidate.evidence),
        "versions": dict(candidate.versions),
        "signature": candidate.signature,
        "status": candidate.status.value,
        "created_at": candidate.created_at,
        "reviewer": candidate.reviewer,
        "review_reason": candidate.review_reason,
        "reviewed_at": candidate.reviewed_at,
        "promoted_at": candidate.promoted_at,
    }


def candidate_from_record(record: RegressionCandidateRecord) -> RegressionCandidate:
    return RegressionCandidate(
        candidate_id=record.candidate_id,
        source_kind=CandidateSource(record.source_kind),
        source_run_id=record.source_run_id,
        source_event_id=record.source_event_id,
        failure_type=record.failure_type,
        sanitized_input=_mapping(record.sanitized_input),
        sanitized_reference=_mapping(record.sanitized_reference),
        evidence=_mapping(record.evidence),
        versions={str(key): str(value) for key, value in record.versions.items()},
        signature=record.signature,
        status=CandidateStatus(record.status),
        created_at=record.created_at,
        reviewer=record.reviewer,
        review_reason=record.review_reason,
        reviewed_at=record.reviewed_at,
        promoted_at=record.promoted_at,
    )


def audit_from_record(record: RegressionAuditRecord) -> RegressionAuditEntry:
    return RegressionAuditEntry(
        candidate_id=record.candidate_id,
        action=AuditAction(record.action),
        actor=record.actor,
        occurred_at=record.occurred_at,
        metadata=_mapping(record.details),
    )


def example_from_record(record: RegressionExampleRecord) -> PromotedRegressionExample:
    return PromotedRegressionExample(
        version=record.version,
        split=record.split,
        candidate_id=record.candidate_id,
        example_id=record.example_id,
        signature=record.signature,
        inputs=_mapping(record.inputs),
        reference_outputs=_mapping(record.reference_outputs),
        metadata=_mapping(record.example_metadata),
        checksum=record.checksum,
        promoted_at=record.promoted_at,
    )


def _mapping(value: Mapping[str, Any]) -> Mapping[str, object]:
    return cast("Mapping[str, object]", dict(value))
