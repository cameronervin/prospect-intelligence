"""Reviewed promotion of sanitized online failures into offline regressions."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from app.features.agent_quality.domain.regression_payloads import (
    CandidateSource,
    RegressionDraft,
    canonical_regression_bytes,
    copy_json_mapping,
    require_machine_key,
)

REGRESSION_DATASET_VERSION = "freight-prospect-regression-v1"
REGRESSION_SPLIT = "regression"


class CandidateStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PROMOTED = "promoted"


class ReviewDecision(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"


class AuditAction(StrEnum):
    CREATED = "created"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PROMOTED = "promoted"


class DuplicateRegressionCandidateError(ValueError):
    def __init__(self, existing_candidate_id: str) -> None:
        self.existing_candidate_id = existing_candidate_id
        super().__init__(f"duplicate regression candidate: {existing_candidate_id}")


@dataclass(frozen=True, slots=True)
class RegressionCandidate:
    candidate_id: str
    source_kind: CandidateSource
    source_run_id: str
    source_event_id: str
    failure_type: str
    sanitized_input: Mapping[str, object]
    sanitized_reference: Mapping[str, object]
    evidence: Mapping[str, object]
    versions: Mapping[str, str]
    signature: str
    status: CandidateStatus
    created_at: datetime
    reviewer: str | None = None
    review_reason: str | None = None
    reviewed_at: datetime | None = None
    promoted_at: datetime | None = None

    @classmethod
    def new(
        cls,
        *,
        candidate_id: str,
        draft: RegressionDraft,
        created_at: datetime,
    ) -> RegressionCandidate:
        if not candidate_id.strip():
            raise ValueError("candidate_id must be non-empty")
        if created_at.tzinfo is None:
            raise ValueError("candidate timestamps must include a timezone")
        draft.validate()
        return cls(
            candidate_id=candidate_id,
            source_kind=draft.source_kind,
            source_run_id=draft.source_run_id,
            source_event_id=draft.source_event_id,
            failure_type=draft.failure_type,
            sanitized_input=copy_json_mapping(draft.sanitized_input),
            sanitized_reference=copy_json_mapping(draft.sanitized_reference),
            evidence=copy_json_mapping(draft.evidence),
            versions={key: value for key, value in sorted(draft.versions.items())},
            signature=draft.signature,
            status=CandidateStatus.PENDING,
            created_at=created_at,
        )

    def review(
        self,
        *,
        decision: ReviewDecision,
        reviewer: str,
        reason: str,
        reviewed_at: datetime,
    ) -> RegressionCandidate:
        if not reviewer.strip():
            raise ValueError("reviewer must be non-empty")
        require_machine_key(reason, name="review reason")
        if reviewed_at.tzinfo is None:
            raise ValueError("review timestamps must include a timezone")
        target = (
            CandidateStatus.ACCEPTED
            if decision is ReviewDecision.ACCEPT
            else CandidateStatus.REJECTED
        )
        if self.status is target and (
            self.reviewer,
            self.review_reason,
            self.reviewed_at,
        ) == (reviewer, reason, reviewed_at):
            return self
        if self.status is not CandidateStatus.PENDING:
            raise ValueError("candidate has already been reviewed")
        return replace(
            self,
            status=target,
            reviewer=reviewer,
            review_reason=reason,
            reviewed_at=reviewed_at,
        )

    def matches_draft(self, draft: RegressionDraft) -> bool:
        """Return whether a repeated intake carries the same complete sanitized draft."""

        return canonical_regression_bytes(
            {
                "source_kind": self.source_kind.value,
                "source_run_id": self.source_run_id,
                "source_event_id": self.source_event_id,
                "failure_type": self.failure_type,
                "input": self.sanitized_input,
                "reference": self.sanitized_reference,
                "evidence": self.evidence,
                "versions": self.versions,
            }
        ) == canonical_regression_bytes(
            {
                "source_kind": draft.source_kind.value,
                "source_run_id": draft.source_run_id,
                "source_event_id": draft.source_event_id,
                "failure_type": draft.failure_type,
                "input": draft.sanitized_input,
                "reference": draft.sanitized_reference,
                "evidence": draft.evidence,
                "versions": draft.versions,
            }
        )

    def promoted(self, *, promoted_at: datetime) -> RegressionCandidate:
        if promoted_at.tzinfo is None:
            raise ValueError("promotion timestamps must include a timezone")
        if self.status is CandidateStatus.PROMOTED:
            return self
        if self.status is not CandidateStatus.ACCEPTED:
            raise ValueError("candidate must be accepted before promotion")
        return replace(self, status=CandidateStatus.PROMOTED, promoted_at=promoted_at)


@dataclass(frozen=True, slots=True)
class RegressionAuditEntry:
    candidate_id: str
    action: AuditAction
    actor: str
    occurred_at: datetime
    metadata: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class PromotedRegressionExample:
    version: str
    split: str
    candidate_id: str
    example_id: str
    signature: str
    inputs: Mapping[str, object]
    reference_outputs: Mapping[str, object]
    metadata: Mapping[str, object]
    checksum: str
    promoted_at: datetime

    @classmethod
    def from_candidate(
        cls,
        candidate: RegressionCandidate,
        *,
        promoted_at: datetime,
    ) -> PromotedRegressionExample:
        RegressionDraft(
            source_kind=candidate.source_kind,
            source_run_id=candidate.source_run_id,
            source_event_id=candidate.source_event_id,
            failure_type=candidate.failure_type,
            sanitized_input=candidate.sanitized_input,
            sanitized_reference=candidate.sanitized_reference,
            evidence=candidate.evidence,
            versions=candidate.versions,
        ).validate()
        if candidate.status not in {CandidateStatus.ACCEPTED, CandidateStatus.PROMOTED}:
            raise ValueError("candidate must be accepted before promotion")
        if candidate.reviewer is None or candidate.reviewed_at is None:
            raise ValueError("candidate review provenance is incomplete")
        example_id = f"regression_{candidate.signature[:24]}"
        inputs = {"example_id": example_id, **dict(candidate.sanitized_input)}
        metadata: dict[str, object] = {
            "failure_type": candidate.failure_type,
            "source_kind": candidate.source_kind.value,
            "source_run_id": candidate.source_run_id,
            "source_event_id": candidate.source_event_id,
            "evidence": dict(candidate.evidence),
            "versions": dict(candidate.versions),
            "reviewer": candidate.reviewer,
            "reviewed_at": candidate.reviewed_at.isoformat(),
        }
        payload: dict[str, object] = {
            "version": REGRESSION_DATASET_VERSION,
            "split": REGRESSION_SPLIT,
            "candidate_id": candidate.candidate_id,
            "example_id": example_id,
            "signature": candidate.signature,
            "inputs": inputs,
            "reference_outputs": dict(candidate.sanitized_reference),
            "metadata": metadata,
            "promoted_at": promoted_at.isoformat(),
        }
        checksum = hashlib.sha256(canonical_regression_bytes(payload)).hexdigest()
        return cls(
            version=REGRESSION_DATASET_VERSION,
            split=REGRESSION_SPLIT,
            candidate_id=candidate.candidate_id,
            example_id=example_id,
            signature=candidate.signature,
            inputs=inputs,
            reference_outputs=dict(candidate.sanitized_reference),
            metadata=metadata,
            checksum=checksum,
            promoted_at=promoted_at,
        )
