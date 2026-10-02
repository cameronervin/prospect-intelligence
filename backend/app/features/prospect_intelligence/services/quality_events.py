"""Best-effort delivery of durable, sanitized quality events."""

import asyncio
import math
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from ..contracts.quality_events import QualityEventOutbox, QualityEventSink

QUALITY_EVENT_DELIVERY_FAILURE = "quality_event_delivery_failed"
DEFAULT_QUALITY_EVENT_PUBLISH_TIMEOUT_SECONDS = 10.0
logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DispatchResult:
    attempted: int
    delivered: int
    failed: int


class QualityEventDispatcher:
    """Publish pending events and acknowledge each only after sink success."""

    def __init__(
        self,
        *,
        outbox: QualityEventOutbox,
        sink: QualityEventSink,
        clock: Callable[[], datetime],
        publish_timeout_seconds: float = DEFAULT_QUALITY_EVENT_PUBLISH_TIMEOUT_SECONDS,
    ) -> None:
        if not math.isfinite(publish_timeout_seconds) or publish_timeout_seconds <= 0:
            raise ValueError("publish_timeout_seconds must be finite and positive")
        self._outbox = outbox
        self._sink = sink
        self._clock = clock
        self._publish_timeout_seconds = publish_timeout_seconds

    async def dispatch_pending(self, *, limit: int = 100) -> DispatchResult:
        pending = await asyncio.to_thread(self._outbox.list_pending, limit)
        delivered = 0
        failed = 0

        for event in pending:
            try:
                await asyncio.wait_for(
                    self._sink.publish(event),
                    timeout=self._publish_timeout_seconds,
                )
                await asyncio.to_thread(
                    self._outbox.mark_delivered,
                    event.event_id,
                    self._clock(),
                )
            except Exception as error:
                failed += 1
                await logger.awarning(
                    "online_quality_event_delivery_failed",
                    event_id=str(event.event_id),
                    error_type=type(error).__name__,
                )
                await self._record_failure(event.event_id)
            else:
                delivered += 1

        return DispatchResult(
            attempted=len(pending),
            delivered=delivered,
            failed=failed,
        )

    async def _record_failure(self, event_id: UUID) -> None:
        # The event remains pending even if recording its delivery attempt fails.
        with suppress(Exception):
            await asyncio.to_thread(
                self._outbox.record_failure,
                event_id,
                QUALITY_EVENT_DELIVERY_FAILURE,
            )
