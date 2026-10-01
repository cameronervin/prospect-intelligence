"""Explicit, reviewed intake of sanitized offline regression examples."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from app.features.agent_quality.contracts.gateways import (
    RegressionDatasetExporter,
    RegressionRepository,
)
from app.features.agent_quality.domain.regression import (
    CandidateSource,
    DuplicateRegressionCandidateError,
    PromotedRegressionExample,
    RegressionCandidate,
    RegressionDraft,
    ReviewDecision,
)


class RegressionWorkflow:
    def __init__(
        self,
        repository: RegressionRepository,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
        exporter: RegressionDatasetExporter | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._exporter = exporter

    async def create_from_online_flag(self, draft: RegressionDraft) -> RegressionCandidate:
        if draft.source_kind is not CandidateSource.ONLINE_FLAG:
            raise ValueError("online flag intake requires source_kind=online_flag")
        return await self._create(draft)

    async def create_from_rep_rejection(self, draft: RegressionDraft) -> RegressionCandidate:
        if draft.source_kind is not CandidateSource.REP_REJECTION:
            raise ValueError("rep rejection intake requires source_kind=rep_rejection")
        return await self._create(draft)

    async def review(
        self,
        candidate_id: str,
        *,
        decision: ReviewDecision,
        reviewer: str,
        reason: str,
    ) -> RegressionCandidate:
        return await self._repository.review(
            candidate_id,
            decision=decision,
            reviewer=reviewer,
            reason=reason,
            reviewed_at=self._clock(),
        )

    async def promote(self, candidate_id: str) -> PromotedRegressionExample:
        candidate = await self._required(candidate_id)
        promoted_at = candidate.promoted_at or self._clock()
        example = PromotedRegressionExample.from_candidate(
            candidate,
            promoted_at=promoted_at,
        )
        promoted = await self._repository.promote(
            candidate_id,
            example=example,
            promoted_at=promoted_at,
        )
        if self._exporter is not None:
            await self.export_snapshot()
        return promoted

    async def export_snapshot(self) -> str:
        if self._exporter is None:
            raise RuntimeError("regression dataset exporter is not configured")
        return await self._exporter.export(await self._repository.list_promoted())

    async def _create(self, draft: RegressionDraft) -> RegressionCandidate:
        draft.validate()
        duplicate = await self._repository.get_by_signature(draft.signature)
        if duplicate is not None:
            if duplicate.matches_draft(draft):
                return duplicate
            raise DuplicateRegressionCandidateError(duplicate.candidate_id)
        candidate = RegressionCandidate.new(
            candidate_id=self._id_factory(),
            draft=draft,
            created_at=self._clock(),
        )
        return await self._repository.create(candidate)

    async def _required(self, candidate_id: str) -> RegressionCandidate:
        candidate = await self._repository.get(candidate_id)
        if candidate is None:
            raise LookupError(f"regression candidate not found: {candidate_id}")
        return candidate
