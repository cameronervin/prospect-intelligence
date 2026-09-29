"""Sanitized cross-feature quality event contract tests."""

from datetime import UTC, datetime
from uuid import UUID

from app.features.prospect_intelligence.public import (
    FitVerdict,
    QualityEvent,
    QualityEventType,
    ReviewAction,
    SourceMode,
)


def test_quality_event_serialization_contains_only_sanitized_allowlist() -> None:
    event = QualityEvent(
        event_id=UUID("00000000-0000-0000-0000-000000000001"),
        run_id=UUID("00000000-0000-0000-0000-000000000002"),
        account_id="acme-foods",
        tenant_id_hash="a" * 64,
        rep_id_hash="b" * 64,
        event_type=QualityEventType.REVIEW_COMPLETED,
        occurred_at=datetime(2026, 9, 29, 12, tzinfo=UTC),
        agent_version="prospect-intelligence-v1",
        prompt_version="v1",
        verdict=FitVerdict.FIT,
        review_decision=ReviewAction.EDIT,
        edit_distance=0.25,
        source_modes=(SourceMode.LIVE, SourceMode.FIXTURE),
    )

    payload = event.to_payload()

    assert payload["tenant_id_hash"] == "a" * 64
    assert payload["source_modes"] == ["live", "fixture"]
    assert set(payload) == {
        "event_id",
        "run_id",
        "account_id",
        "tenant_id_hash",
        "rep_id_hash",
        "event_type",
        "occurred_at",
        "agent_version",
        "prompt_version",
        "verdict",
        "review_decision",
        "edit_distance",
        "source_modes",
        "error_code",
    }
    assert not {
        "tenant_id",
        "rep_id",
        "prompt",
        "draft",
        "contact",
        "credentials",
        "provider_payload",
        "model_output",
    }.intersection(payload)
