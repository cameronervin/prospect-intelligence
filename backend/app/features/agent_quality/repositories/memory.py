"""In-memory regression repository for tests and local demonstrations."""

from app.features.agent_quality.domain.regression import RegressionCandidate


class InMemoryRegressionRepository:
    def __init__(self) -> None:
        self._candidates: dict[str, RegressionCandidate] = {}

    async def save(self, candidate: RegressionCandidate) -> None:
        self._candidates[candidate.candidate_id] = candidate

    async def get(self, candidate_id: str) -> RegressionCandidate | None:
        return self._candidates.get(candidate_id)
