"""Provision rules and route failed online signals for human review."""

from collections.abc import Sequence

from app.features.agent_quality.contracts.gateways import LangSmithQualityGateway
from app.features.agent_quality.contracts.models import (
    OnlineQualityConfig,
    QualitySignal,
)
from app.features.prospect_intelligence.public import QualityEvent


class OnlineQualityService:
    def __init__(self, *, gateway: LangSmithQualityGateway, config: OnlineQualityConfig) -> None:
        self._gateway = gateway
        self._config = config

    async def provision(self) -> None:
        await self._gateway.configure(self._config)

    async def observe(self, event: QualityEvent, signals: Sequence[QualitySignal]) -> None:
        """Record sanitized feedback and route each failed invariant once."""

        await self._gateway.record_event(event.to_payload())
        for signal in signals:
            await self._gateway.record_feedback(str(event.run_id), signal)
            if not signal.passed:
                await self._gateway.route_annotation(str(event.run_id), signal.key)
