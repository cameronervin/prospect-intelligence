"""Explicit review workflow for durable regression candidates."""

from app.features.agent_quality.contracts.gateways import RegressionRepository
from app.features.agent_quality.domain.regression import RegressionCandidate


class RegressionWorkflow:
    def __init__(self, repository: RegressionRepository) -> None:
        self._repository = repository

    async def review(
        self, candidate_id: str, *, accepted: bool, reviewer: str
    ) -> RegressionCandidate:
        candidate = await self._required(candidate_id)
        reviewed = candidate.review(accepted=accepted, reviewer=reviewer)
        await self._repository.save(reviewed)
        return reviewed

    async def promote(self, candidate_id: str) -> dict[str, object]:
        candidate = await self._required(candidate_id)
        if candidate.reviewer is None:
            raise ValueError("candidate must be reviewed before promotion")
        promoted = candidate.promoted()
        await self._repository.save(promoted)
        return {
            "version": "regression-v1",
            "split": "regression",
            "candidate_id": promoted.candidate_id,
            "source_run_id": promoted.source_run_id,
            "failure_type": promoted.failure_type,
            "input": dict(promoted.sanitized_input),
            "reference": dict(promoted.sanitized_reference),
        }

    async def _required(self, candidate_id: str) -> RegressionCandidate:
        candidate = await self._repository.get(candidate_id)
        if candidate is None:
            raise LookupError(f"regression candidate not found: {candidate_id}")
        return candidate
