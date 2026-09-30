"""Quality-event outbox contract and record-shape tests."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy import Table, UniqueConstraint

from app.features.agent_quality.contracts.models import (
    EvaluationSamplingDecision,
    QualityEvaluationEnvelope,
    QualitySignal,
)
from app.features.prospect_intelligence.contracts.models import (
    QualityEvent,
    QualityEventType,
)
from app.features.prospect_intelligence.contracts.quality_events import (
    QualityEventOutbox,
    QualityEventSink,
)
from app.features.prospect_intelligence.models.records import QualityEventOutboxRecord
from app.features.prospect_intelligence.repositories.postgres.quality_events import (
    quality_event_from_payload,
)


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


def test_outbox_decoder_restores_sampling_decision_without_an_envelope() -> None:
    event = QualityEvent(
        event_id=UUID("00000000-0000-0000-0000-000000000001"),
        run_id=UUID("00000000-0000-0000-0000-000000000002"),
        account_id="account-safe-id",
        tenant_id_hash="a" * 64,
        rep_id_hash="b" * 64,
        event_type=QualityEventType.ANALYSIS_COMPLETED,
        occurred_at=datetime(2026, 9, 29, 12, tzinfo=UTC),
        agent_version="prospect-intelligence-v1",
        prompt_version="v1",
        evaluation_sampling=EvaluationSamplingDecision(
            selected=False,
            sample_rate=0.1,
            policy_version="sha256-run-id-v1",
        ),
    )

    assert quality_event_from_payload(event.to_storage_payload()) == event


def test_outbox_decoder_restores_selected_decision_with_its_envelope() -> None:
    event = QualityEvent(
        event_id=UUID("00000000-0000-0000-0000-000000000001"),
        run_id=UUID("00000000-0000-0000-0000-000000000002"),
        account_id="account-safe-id",
        tenant_id_hash="a" * 64,
        rep_id_hash="b" * 64,
        event_type=QualityEventType.ANALYSIS_COMPLETED,
        occurred_at=datetime(2026, 9, 29, 12, tzinfo=UTC),
        agent_version="prospect-intelligence-v1",
        prompt_version="v1",
        evaluation=QualityEvaluationEnvelope(
            evaluator_version="freight-evaluators-v2",
            graph_revision="graph-v1",
            rubric_version="semantic-v1",
            deterministic_signals=(QualitySignal(key="trajectory_checks", score=1.0, passed=True),),
        ),
        evaluation_sampling=EvaluationSamplingDecision(
            selected=True,
            sample_rate=0.1,
            policy_version="sha256-run-id-v1",
        ),
    )

    assert quality_event_from_payload(event.to_storage_payload()) == event


def test_outbox_decoder_accepts_legacy_analysis_event_without_sampling_marker() -> None:
    event = QualityEvent(
        event_id=UUID("00000000-0000-0000-0000-000000000001"),
        run_id=UUID("00000000-0000-0000-0000-000000000002"),
        account_id="account-safe-id",
        tenant_id_hash="a" * 64,
        rep_id_hash="b" * 64,
        event_type=QualityEventType.ANALYSIS_COMPLETED,
        occurred_at=datetime(2026, 9, 29, 12, tzinfo=UTC),
        agent_version="prospect-intelligence-v1",
        prompt_version="v1",
    )

    assert quality_event_from_payload(event.to_storage_payload()) == event


def test_outbox_decoder_rejects_partial_sampling_marker() -> None:
    event = QualityEvent(
        event_id=UUID("00000000-0000-0000-0000-000000000001"),
        run_id=UUID("00000000-0000-0000-0000-000000000002"),
        account_id="account-safe-id",
        tenant_id_hash="a" * 64,
        rep_id_hash="b" * 64,
        event_type=QualityEventType.ANALYSIS_COMPLETED,
        occurred_at=datetime(2026, 9, 29, 12, tzinfo=UTC),
        agent_version="prospect-intelligence-v1",
        prompt_version="v1",
    )

    with pytest.raises(ValueError, match="incomplete evaluation sampling"):
        quality_event_from_payload({**event.to_storage_payload(), "evaluation_sampled": False})
