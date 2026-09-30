"""Focused tests for at-least-once quality-event dispatch."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from app.features.prospect_intelligence.contracts.models import (
    QualityEvent,
    QualityEventType,
)
from app.features.prospect_intelligence.services.quality_events import (
    QUALITY_EVENT_DELIVERY_FAILURE,
    QualityEventDispatcher,
)


def _event(sequence: int) -> QualityEvent:
    return QualityEvent(
        event_id=UUID(int=sequence),
        run_id=UUID(int=sequence + 100),
        account_id=f"account-{sequence}",
        tenant_id_hash="a" * 64,
        rep_id_hash="b" * 64,
        event_type=QualityEventType.RUN_CREATED,
        occurred_at=datetime(2026, 9, 29, 12, tzinfo=UTC),
        agent_version="prospect-intelligence-v1",
        prompt_version="v1",
    )


class _Outbox:
    def __init__(self, events: tuple[QualityEvent, ...]) -> None:
        self.events = events
        self.requested_limits: list[int] = []
        self.delivered: list[tuple[UUID, datetime]] = []
        self.failures: list[tuple[UUID, str]] = []

    def list_pending(self, limit: int) -> tuple[QualityEvent, ...]:
        self.requested_limits.append(limit)
        return self.events[:limit]

    def mark_delivered(self, event_id: UUID, delivered_at: datetime) -> None:
        self.delivered.append((event_id, delivered_at))

    def record_failure(self, event_id: UUID, error_code: str) -> None:
        self.failures.append((event_id, error_code))


class _Sink:
    def __init__(self, fail_for: UUID | None = None) -> None:
        self.fail_for = fail_for
        self.published: list[QualityEvent] = []

    async def publish(self, event: QualityEvent) -> None:
        self.published.append(event)
        if event.event_id == self.fail_for:
            raise RuntimeError("provider response contained secret-token-value")


async def test_dispatcher_marks_events_delivered_only_after_publish() -> None:
    events = (_event(1), _event(2))
    outbox = _Outbox(events)
    sink = _Sink()
    now = datetime(2026, 9, 29, 13, tzinfo=UTC)

    def clock() -> datetime:
        return now

    dispatcher = QualityEventDispatcher(outbox=outbox, sink=sink, clock=clock)

    result = await dispatcher.dispatch_pending(limit=10)

    assert result.attempted == 2
    assert result.delivered == 2
    assert result.failed == 0
    assert outbox.requested_limits == [10]
    assert sink.published == list(events)
    assert outbox.delivered == [(event.event_id, now) for event in events]
    assert outbox.failures == []


async def test_dispatcher_records_sanitized_failure_and_continues() -> None:
    events = (_event(1), _event(2), _event(3))
    outbox = _Outbox(events)
    sink = _Sink(fail_for=events[1].event_id)
    now = datetime(2026, 9, 29, 13, tzinfo=UTC)
    dispatcher = QualityEventDispatcher(outbox=outbox, sink=sink, clock=lambda: now)

    result = await dispatcher.dispatch_pending()

    assert result.attempted == 3
    assert result.delivered == 2
    assert result.failed == 1
    assert sink.published == list(events)
    assert outbox.delivered == [
        (events[0].event_id, now),
        (events[2].event_id, now),
    ]
    assert outbox.failures == [(events[1].event_id, QUALITY_EVENT_DELIVERY_FAILURE)]
    assert "secret-token-value" not in repr(outbox.failures)


async def test_dispatcher_leaves_event_pending_when_delivery_marker_fails() -> None:
    event = _event(1)

    class _MarkerFailureOutbox(_Outbox):
        def mark_delivered(self, event_id: UUID, delivered_at: datetime) -> None:
            raise RuntimeError("database credentials leaked here")

    outbox = _MarkerFailureOutbox((event,))
    dispatcher = QualityEventDispatcher(
        outbox=outbox,
        sink=_Sink(),
        clock=lambda: datetime(2026, 9, 29, 13, tzinfo=UTC),
    )

    result = await dispatcher.dispatch_pending()

    assert result.attempted == 1
    assert result.delivered == 0
    assert result.failed == 1
    assert outbox.failures == [(event.event_id, QUALITY_EVENT_DELIVERY_FAILURE)]


async def test_dispatcher_times_out_a_hung_sink_and_continues_the_batch() -> None:
    events = (_event(1), _event(2))

    class _HungFirstSink(_Sink):
        async def publish(self, event: QualityEvent) -> None:
            self.published.append(event)
            if event == events[0]:
                await asyncio.Event().wait()

    outbox = _Outbox(events)
    sink = _HungFirstSink()
    now = datetime(2026, 9, 29, 13, tzinfo=UTC)
    dispatcher = QualityEventDispatcher(
        outbox=outbox,
        sink=sink,
        clock=lambda: now,
        publish_timeout_seconds=0.01,
    )

    result = await dispatcher.dispatch_pending()

    assert result.attempted == 2
    assert result.delivered == 1
    assert result.failed == 1
    assert sink.published == list(events)
    assert outbox.delivered == [(events[1].event_id, now)]
    assert outbox.failures == [(events[0].event_id, QUALITY_EVENT_DELIVERY_FAILURE)]
