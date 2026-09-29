"""Review state for promoting production failures into offline regressions."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum


class CandidateStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PROMOTED = "promoted"


@dataclass(frozen=True, slots=True)
class RegressionCandidate:
    candidate_id: str
    source_run_id: str
    failure_type: str
    sanitized_input: Mapping[str, object]
    sanitized_reference: Mapping[str, object]
    status: CandidateStatus
    reviewer: str | None = None

    @classmethod
    def new(
        cls,
        *,
        candidate_id: str,
        source_run_id: str,
        failure_type: str,
        sanitized_input: Mapping[str, object],
        sanitized_reference: Mapping[str, object],
    ) -> "RegressionCandidate":
        if not all((candidate_id, source_run_id, failure_type)):
            raise ValueError("candidate identifiers and failure type must be non-empty")
        return cls(
            candidate_id=candidate_id,
            source_run_id=source_run_id,
            failure_type=failure_type,
            sanitized_input=dict(sanitized_input),
            sanitized_reference=dict(sanitized_reference),
            status=CandidateStatus.PENDING,
        )

    def review(self, *, accepted: bool, reviewer: str) -> "RegressionCandidate":
        if self.status is not CandidateStatus.PENDING:
            raise ValueError("candidate has already been reviewed")
        if not reviewer.strip():
            raise ValueError("reviewer must be non-empty")
        status = CandidateStatus.ACCEPTED if accepted else CandidateStatus.REJECTED
        return replace(self, status=status, reviewer=reviewer)

    def promoted(self) -> "RegressionCandidate":
        if self.status is not CandidateStatus.ACCEPTED:
            raise ValueError("candidate must be accepted before promotion")
        return replace(self, status=CandidateStatus.PROMOTED)
