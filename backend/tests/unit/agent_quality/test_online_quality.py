"""Online quality configuration and feedback tests."""

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.features.agent_quality.contracts.models import (
    OnlineQualityConfig,
    QualitySignal,
)
from app.features.agent_quality.services.online_quality import OnlineQualityService
from app.features.prospect_intelligence.public import QualityEvent, QualityEventType


class RecordingGateway:
    def __init__(self) -> None:
        self.configured: list[OnlineQualityConfig] = []
        self.events: list[Mapping[str, object]] = []
        self.feedback: list[tuple[str, QualitySignal]] = []
        self.annotations: list[tuple[str, str]] = []

    async def configure(self, config: OnlineQualityConfig) -> None:
        self.configured.append(config)

    async def record_event(self, payload: Mapping[str, object]) -> None:
        self.events.append(payload)

    async def record_feedback(self, run_id: str, signal: QualitySignal) -> None:
        self.feedback.append((run_id, signal))

    async def route_annotation(self, run_id: str, reason: str) -> None:
        self.annotations.append((run_id, reason))


@pytest.mark.asyncio
async def test_online_service_configures_injected_gateway_and_routes_failures() -> None:
    gateway = RecordingGateway()
    config = OnlineQualityConfig.default()
    service = OnlineQualityService(gateway=gateway, config=config)
    event = QualityEvent(
        event_id=UUID("00000000-0000-0000-0000-000000000001"),
        run_id=UUID("00000000-0000-0000-0000-000000000123"),
        account_id="syn_live_01",
        tenant_id_hash="0" * 64,
        rep_id_hash="1" * 64,
        event_type=QualityEventType.ANALYSIS_COMPLETED,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        agent_version="graph-v1",
        prompt_version="prompt-v1",
    )

    await service.provision()
    await service.observe(
        event,
        (
            QualitySignal(key="numeric_groundedness", score=0.0, passed=False),
            QualitySignal(key="trajectory_checks", score=1.0, passed=True),
        ),
    )

    assert gateway.configured == [config]
    assert gateway.events == [event.to_payload()]
    assert len(gateway.feedback) == 2
    assert gateway.annotations == [("00000000-0000-0000-0000-000000000123", "numeric_groundedness")]
