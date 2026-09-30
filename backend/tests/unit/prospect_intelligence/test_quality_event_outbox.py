"""Quality-event outbox contract and record-shape tests."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import Table, UniqueConstraint

from app.features.prospect_intelligence.contracts.models import (
    QualityEvent,
    QualityEventType,
)
from app.features.prospect_intelligence.contracts.quality_events import (
    QualityEventOutbox,
    QualityEventSink,
)
from app.features.prospect_intelligence.models.records import QualityEventOutboxRecord


class _Sink:
    async def publish(self, event: QualityEvent) -> None:
        del event


class _Outbox:
    def list_pending(self, limit: int) -> tuple[QualityEvent, ...]:
        del limit
        return ()

    def mark_delivered(self, event_id: UUID, delivered_at: datetime) -> None:
        del event_id, delivered_at

    def record_failure(self, event_id: UUID, error_code: str) -> None:
        del event_id, error_code


def test_quality_event_ports_are_structurally_implementable() -> None:
    sink: QualityEventSink = _Sink()
    outbox: QualityEventOutbox = _Outbox()

    assert sink is not None
    assert outbox.list_pending(10) == ()


def test_quality_event_outbox_record_has_deterministic_identity_and_delivery_state() -> None:
    table = cast("Table", QualityEventOutboxRecord.__table__)

    assert table.c.event_id.primary_key
    assert table.c.payload.nullable is False
    assert table.c.delivery_attempts.default is not None
    assert table.c.delivered_at.nullable is True
    assert table.c.last_error_code.nullable is True
    assert any(
        isinstance(constraint, UniqueConstraint)
        and {column.name for column in constraint.columns} == {"run_id", "event_type"}
        for constraint in table.constraints
    )


def test_quality_event_fixture_remains_sanitized() -> None:
    event = QualityEvent(
        event_id=UUID("00000000-0000-0000-0000-000000000001"),
        run_id=UUID("00000000-0000-0000-0000-000000000002"),
        account_id="account-safe-id",
        tenant_id_hash="a" * 64,
        rep_id_hash="b" * 64,
        event_type=QualityEventType.RUN_CREATED,
        occurred_at=datetime(2026, 9, 29, 12, tzinfo=UTC),
        agent_version="prospect-intelligence-v1",
        prompt_version="v1",
    )

    assert set(event.to_payload()).isdisjoint({"tenant_id", "rep_id", "draft", "prompt"})
