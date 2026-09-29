"""Credential-free worker behavior for the local demo."""

from datetime import UTC, datetime

from app.features.prospect_intelligence.contracts.models import RunStatus
from app.features.prospect_intelligence.fixtures.synthetic import SyntheticSourceCatalog
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
from tests.fakes import synthetic_prospect_sources


def test_pipeline_produces_reviewable_fit_from_seeded_evidence() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run("tenant-demo", "rep-demo", "acme-foods")

    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)

    completed = service.get_run(run.id)
    assert completed.status is RunStatus.AWAITING_REVIEW
    assert completed.output is not None
    assert completed.output.verdict.value == "fit"
    assert completed.output.brief.lanes[0].score.matched_loads_per_week == 31
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

    DeterministicProspectPipeline(
        service,
        synthetic_prospect_sources(aliases={"northstar-retail": "edge_01"}),
    ).run(run.id)

    completed = service.get_run(run.id)
    assert completed.status is RunStatus.COMPLETED
    assert completed.output is not None
    assert completed.output.verdict.value == "needs_more_data"


def test_pipeline_matches_each_default_alias_scenario_reference() -> None:
    catalog = SyntheticSourceCatalog.reviewed()
    for account_id in ("acme-foods", "northstar-retail"):
        service = ProspectRunService(
            accounts=InMemoryAccountRepository.seeded(),
            runs=InMemoryRunRepository(),
            receipts=InMemorySendReceiptRepository(),
            preferences=InMemoryPreferenceRepository(),
            clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
        )
        run = service.create_run("tenant-demo", "rep-demo", account_id)
        DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)
        completed = service.get_run(run.id)
        scenario = catalog.scenario_for_account(account_id)
        assert scenario is not None
        assert completed.output is not None
        assert tuple(lane.score for lane in completed.output.brief.lanes) == (
            scenario.reference.expected_lane_scores
        )


def test_pipeline_abstains_when_freight_coverage_is_degraded() -> None:
    for scenario_id in ("edge_03", "edge_06"):
        service = ProspectRunService(
            accounts=InMemoryAccountRepository.seeded(),
            runs=InMemoryRunRepository(),
            receipts=InMemorySendReceiptRepository(),
            preferences=InMemoryPreferenceRepository(),
            clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
        )
        run = service.create_run("tenant-demo", "rep-demo", "acme-foods")
        DeterministicProspectPipeline(
            service,
            synthetic_prospect_sources(aliases={"acme-foods": scenario_id}),
        ).run(run.id)
        completed = service.get_run(run.id)
        assert completed.output is not None
        assert completed.output.verdict.value == "needs_more_data"
        assert completed.output.outreach is None
