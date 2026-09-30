"""Injected app-side evaluation boundary for completed graph state."""

from collections.abc import Mapping
from typing import Protocol
from uuid import UUID

from app.features.agent_quality.contracts.models import QualityEvaluationProjection

from .models import AnalysisOutput


class OnlineQualityProjector(Protocol):
    def project(
        self,
        *,
        run_id: UUID,
        files: Mapping[str, object],
        raw_state: Mapping[str, object],
        account_name: str,
        rep_preferences: tuple[str, ...],
        latency_seconds: float,
        analysis_output: AnalysisOutput,
        injection_canary: str | None = None,
    ) -> QualityEvaluationProjection: ...
