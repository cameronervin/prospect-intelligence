"""Ports for sanitized online-quality event delivery."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from .models import QualityEvent


class QualityEventSink(Protocol):
    """Async boundary implemented by downstream quality integrations."""

    async def publish(self, event: QualityEvent) -> None: ...


class QualityEventOutbox(Protocol):
    """Durable pending-event boundary used by the delivery dispatcher."""

    def list_pending(self, limit: int) -> tuple[QualityEvent, ...]: ...

    def mark_delivered(self, event_id: UUID, delivered_at: datetime) -> None: ...

    def record_failure(self, event_id: UUID, error_code: str) -> None: ...
