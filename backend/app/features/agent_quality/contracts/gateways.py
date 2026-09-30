"""Injected I/O boundaries used by agent-quality services."""

from collections.abc import Mapping
from typing import Protocol

from app.features.agent_quality.contracts.models import QualitySignal
from app.features.agent_quality.contracts.online_config import OnlineQualityConfig
from app.features.agent_quality.domain.regression import RegressionCandidate


class LangSmithQualityGateway(Protocol):
    async def configure(self, config: OnlineQualityConfig) -> None: ...

    async def record_event(self, payload: Mapping[str, object]) -> None: ...

    async def record_feedback(self, run_id: str, signal: QualitySignal) -> None: ...

    async def route_annotation(self, run_id: str, reason: str) -> None: ...

    async def aclose(self) -> None: ...


class RegressionRepository(Protocol):
    async def save(self, candidate: RegressionCandidate) -> None: ...

    async def get(self, candidate_id: str) -> RegressionCandidate | None: ...
