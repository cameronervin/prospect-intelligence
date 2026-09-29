"""Credential-free worker behavior for the local demo."""

from datetime import UTC, datetime

from app.features.prospect_intelligence.contracts.models import RunStatus
from app.features.prospect_intelligence.integrations.synthetic import seeded_source_data
from app.features.prospect_intelligence.repositories.memory import (
    InMemoryAccountRepository,
    InMemoryPreferenceRepository,
    InMemoryRunRepository,
    InMemorySendReceiptRepository,
)
from app.features.prospect_intelligence.services.deterministic_pipeline import (
    DeterministicProspectPipeline,
)
from app.features.prospect_intelligence.services.runs import ProspectRunService


def test_pipeline_produces_reviewable_fit_from_seeded_evidence() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run("tenant-demo", "rep-demo", "acme-foods")

    DeterministicProspectPipeline(service, seeded_source_data()).run(run.id)

    completed = service.get_run(run.id)
    assert completed.status is RunStatus.AWAITING_REVIEW
    assert completed.output is not None
    assert completed.output.verdict.value == "fit"
    assert completed.output.brief.lanes[0].score.matched_loads_per_week == 8
    assert completed.output.brief.lanes[0].evidence[0].provenance.mode.value == "fixture"


def test_pipeline_returns_needs_more_data_without_lane_evidence() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run("tenant-demo", "rep-demo", "northstar-retail")

    DeterministicProspectPipeline(service, seeded_source_data()).run(run.id)

    completed = service.get_run(run.id)
    assert completed.status is RunStatus.COMPLETED
    assert completed.output is not None
    assert completed.output.verdict.value == "needs_more_data"
