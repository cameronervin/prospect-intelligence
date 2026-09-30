"""Credential-free gateway fakes for local development and tests."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from app.features.agent_quality.contracts.models import QualitySignal
from app.features.agent_quality.contracts.online_config import OnlineQualityConfig


class NoOpLangSmithQualityGateway:
    """Explicit offline sink; bootstrap must never use this when delivery is enabled."""

    async def configure(self, config: OnlineQualityConfig) -> None:
        del config

    async def record_event(self, payload: Mapping[str, object]) -> None:
        del payload

    async def record_feedback(self, run_id: str, signal: QualitySignal) -> None:
        del run_id, signal

    async def route_annotation(self, run_id: str, reason: str) -> None:
        del run_id, reason

    async def aclose(self) -> None:
        return None


@dataclass(slots=True)
class RecordingLangSmithQualityGateway:
    """Inspectable offline sink implementing the quality gateway protocol."""

    configured: list[OnlineQualityConfig] = field(default_factory=lambda: [])
    events: list[Mapping[str, object]] = field(default_factory=lambda: [])
    feedback: list[tuple[str, QualitySignal]] = field(default_factory=lambda: [])
    annotations: list[tuple[str, str]] = field(default_factory=lambda: [])

    async def configure(self, config: OnlineQualityConfig) -> None:
        self.configured.append(config)

    async def record_event(self, payload: Mapping[str, object]) -> None:
        self.events.append(payload)

    async def record_feedback(self, run_id: str, signal: QualitySignal) -> None:
        self.feedback.append((run_id, signal))

    async def route_annotation(self, run_id: str, reason: str) -> None:
        self.annotations.append((run_id, reason))

    async def aclose(self) -> None:
        return None
