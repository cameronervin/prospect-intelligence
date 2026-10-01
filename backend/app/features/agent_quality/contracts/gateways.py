"""Injected I/O boundaries used by agent-quality services."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol

from app.features.agent_quality.contracts.models import QualitySignal
from app.features.agent_quality.contracts.online_config import OnlineQualityConfig
from app.features.agent_quality.domain.regression import (
    PromotedRegressionExample,
    RegressionAuditEntry,
    RegressionCandidate,
    ReviewDecision,
)


class LangSmithQualityGateway(Protocol):
    async def configure(self, config: OnlineQualityConfig) -> None: ...

    async def record_event(self, payload: Mapping[str, object]) -> None: ...

    async def record_feedback(self, run_id: str, signal: QualitySignal) -> None: ...

    async def route_annotation(self, run_id: str, reason: str) -> None: ...

    async def aclose(self) -> None: ...


class RegressionRepository(Protocol):
    async def create(self, candidate: RegressionCandidate) -> RegressionCandidate: ...

    async def get(self, candidate_id: str) -> RegressionCandidate | None: ...

    async def get_by_signature(self, signature: str) -> RegressionCandidate | None: ...

    async def review(
        self,
        candidate_id: str,
        *,
        decision: ReviewDecision,
        reviewer: str,
        reason: str,
        reviewed_at: datetime,
    ) -> RegressionCandidate: ...

    async def promote(
        self,
        candidate_id: str,
        *,
        example: PromotedRegressionExample,
        promoted_at: datetime,
    ) -> PromotedRegressionExample: ...

    async def list_audit(self, candidate_id: str) -> tuple[RegressionAuditEntry, ...]: ...

    async def list_promoted(self) -> tuple[PromotedRegressionExample, ...]: ...


class RegressionDatasetExporter(Protocol):
    async def export(self, examples: Sequence[PromotedRegressionExample]) -> str: ...
