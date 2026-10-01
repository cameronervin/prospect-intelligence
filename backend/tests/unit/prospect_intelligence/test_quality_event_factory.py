"""Deterministic lifecycle-event construction and sanitization."""

from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256

from app.features.prospect_intelligence.contracts.models import (
    QualityEventType,
    ReviewAction,
)
from app.features.prospect_intelligence.domain.quality_events import build_quality_event
from app.features.prospect_intelligence.repositories.memory import (
    InMemoryAccountRepository,
    InMemoryPreferenceRepository,
    InMemoryRunRepository,
    InMemorySendReceiptRepository,
)
from app.features.prospect_intelligence.services.runs import ProspectRunService
from tests.fakes import auth_context


def build_service() -> ProspectRunService:
    return ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )


def test_quality_event_factory_is_deterministic_and_sanitized() -> None:
    service = build_service()
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")

    first = build_quality_event(run, QualityEventType.RUN_CREATED)
    second = build_quality_event(run, QualityEventType.RUN_CREATED)

    assert second == first
    assert first.tenant_id_hash == sha256(b"tenant-demo").hexdigest()
    assert first.rep_id_hash == sha256(b"rep-demo").hexdigest()
    assert first.account_id == "acme-foods"
    payload = first.to_payload()
    assert "tenant-demo" not in str(payload)
    assert "rep-demo" not in str(payload)
    assert "outreach" not in payload


def test_review_event_carries_only_decision_and_normalized_edit_feedback() -> None:
    service = build_service()
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    reviewed = replace(run, review_action=ReviewAction.EDIT)

    event = build_quality_event(
        reviewed,
        QualityEventType.REVIEW_COMPLETED,
        edit_distance=0.375,
    )

    assert event.review_decision is ReviewAction.EDIT
    assert event.edit_distance == 0.375
    assert event.error_code is None
