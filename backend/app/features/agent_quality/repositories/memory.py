"""In-memory regression repository for focused service tests."""

import asyncio
from datetime import datetime

from app.features.agent_quality.domain.regression import (
    AuditAction,
    CandidateStatus,
    DuplicateRegressionCandidateError,
    PromotedRegressionExample,
    RegressionAuditEntry,
    RegressionCandidate,
    ReviewDecision,
)


class InMemoryRegressionRepository:
    def __init__(self) -> None:
        self._candidates: dict[str, RegressionCandidate] = {}
        self._signatures: dict[str, str] = {}
        self._audits: dict[str, list[RegressionAuditEntry]] = {}
        self._promoted: dict[str, PromotedRegressionExample] = {}
        self._lock = asyncio.Lock()

    async def create(self, candidate: RegressionCandidate) -> RegressionCandidate:
        async with self._lock:
            existing = self._candidates.get(candidate.candidate_id)
            if existing is not None:
                if existing == candidate:
                    return existing
                raise ValueError("candidate identifier already exists with different data")
            duplicate_id = self._signatures.get(candidate.signature)
            if duplicate_id is not None:
                raise DuplicateRegressionCandidateError(duplicate_id)
            self._candidates[candidate.candidate_id] = candidate
            self._signatures[candidate.signature] = candidate.candidate_id
            self._audits[candidate.candidate_id] = [
                RegressionAuditEntry(
                    candidate_id=candidate.candidate_id,
                    action=AuditAction.CREATED,
                    actor=candidate.source_kind.value,
                    occurred_at=candidate.created_at,
                    metadata={
                        "source_run_id": candidate.source_run_id,
                        "source_event_id": candidate.source_event_id,
                    },
                )
            ]
            return candidate

    async def get(self, candidate_id: str) -> RegressionCandidate | None:
        return self._candidates.get(candidate_id)

    async def get_by_signature(self, signature: str) -> RegressionCandidate | None:
        candidate_id = self._signatures.get(signature)
        return self._candidates.get(candidate_id) if candidate_id is not None else None

    async def review(
        self,
        candidate_id: str,
        *,
        decision: ReviewDecision,
        reviewer: str,
        reason: str,
        reviewed_at: datetime,
    ) -> RegressionCandidate:
        async with self._lock:
            candidate = self._required(candidate_id)
            target = (
                CandidateStatus.ACCEPTED
                if decision is ReviewDecision.ACCEPT
                else CandidateStatus.REJECTED
            )
            accepted_after_promotion = (
                target is CandidateStatus.ACCEPTED and candidate.status is CandidateStatus.PROMOTED
            )
            if (candidate.status is target or accepted_after_promotion) and (
                candidate.reviewer,
                candidate.review_reason,
            ) == (reviewer, reason):
                return candidate
            reviewed = candidate.review(
                decision=decision,
                reviewer=reviewer,
                reason=reason,
                reviewed_at=reviewed_at,
            )
            self._candidates[candidate_id] = reviewed
            action = (
                AuditAction.ACCEPTED if decision is ReviewDecision.ACCEPT else AuditAction.REJECTED
            )
            self._audits[candidate_id].append(
                RegressionAuditEntry(
                    candidate_id=candidate_id,
                    action=action,
                    actor=reviewer,
                    occurred_at=reviewed_at,
                    metadata={"reason": reason},
                )
            )
            return reviewed

    async def promote(
        self,
        candidate_id: str,
        *,
        example: PromotedRegressionExample,
        promoted_at: datetime,
    ) -> PromotedRegressionExample:
        async with self._lock:
            candidate = self._required(candidate_id)
            existing = self._promoted.get(candidate_id)
            if existing is not None:
                submitted = PromotedRegressionExample.from_candidate(
                    candidate,
                    promoted_at=promoted_at,
                )
                persisted_at = candidate.promoted_at
                if persisted_at is None:  # pragma: no cover - in-memory invariant
                    raise RuntimeError("promoted candidate has no promotion timestamp")
                persisted = PromotedRegressionExample.from_candidate(
                    candidate,
                    promoted_at=persisted_at,
                )
                if example == submitted and existing == persisted:
                    return existing
                raise ValueError("candidate has a conflicting promotion")
            expected = PromotedRegressionExample.from_candidate(
                candidate,
                promoted_at=promoted_at,
            )
            if example != expected:
                raise ValueError("promoted example does not match accepted candidate")
            promoted = candidate.promoted(promoted_at=promoted_at)
            self._candidates[candidate_id] = promoted
            self._promoted[candidate_id] = example
            self._audits[candidate_id].append(
                RegressionAuditEntry(
                    candidate_id=candidate_id,
                    action=AuditAction.PROMOTED,
                    actor=candidate.reviewer or "system",
                    occurred_at=promoted_at,
                    metadata={"example_id": example.example_id, "checksum": example.checksum},
                )
            )
            return example

    async def list_audit(self, candidate_id: str) -> tuple[RegressionAuditEntry, ...]:
        self._required(candidate_id)
        return tuple(self._audits[candidate_id])

    async def list_promoted(self) -> tuple[PromotedRegressionExample, ...]:
        return tuple(sorted(self._promoted.values(), key=lambda example: example.example_id))

    def _required(self, candidate_id: str) -> RegressionCandidate:
        candidate = self._candidates.get(candidate_id)
        if candidate is None:
            raise LookupError(f"regression candidate not found: {candidate_id}")
        return candidate
