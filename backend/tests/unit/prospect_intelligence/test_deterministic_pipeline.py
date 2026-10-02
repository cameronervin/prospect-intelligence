"""Credential-free worker behavior for the local demo."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.features.prospect_intelligence.contracts.models import RunStatus
from app.features.prospect_intelligence.contracts.sources import (
    CarrierNetwork,
    CarrierNetworkSource,
    SourceCallContext,
    SourceResult,
)
from app.features.prospect_intelligence.domain.models import NetworkLane
from app.features.prospect_intelligence.fixtures.synthetic import SyntheticSourceCatalog
from app.features.prospect_intelligence.repositories.memory import (
    InMemoryPreferenceRepository,
    InMemoryRunRepository,
    InMemorySendReceiptRepository,
)
from app.features.prospect_intelligence.services.runs import ProspectRunService
from tests.deterministic_pipeline import DeterministicProspectPipeline
from tests.fakes import auth_context, synthetic_prospect_sources
from tests.prospect_repositories import InMemoryAccountRepository


class _DuplicateNetworkSource:
    def __init__(self, delegate: CarrierNetworkSource) -> None:
        self._delegate = delegate

    def get_network(self, context: SourceCallContext) -> SourceResult[CarrierNetwork]:
        result = self._delegate.get_network(context)
        assert result.value is not None
        return replace(
            result,
            value=CarrierNetwork(lanes=(*result.value.lanes, result.value.lanes[0])),
        )


class _MalformedNetworkSource:
    def __init__(self, delegate: CarrierNetworkSource) -> None:
        self._delegate = delegate

    def get_network(self, context: SourceCallContext) -> SourceResult[CarrierNetwork]:
        result = self._delegate.get_network(context)
        assert result.value is not None
        valid = result.value.lanes[0]
        malformed = object.__new__(NetworkLane)
        object.__setattr__(malformed, "origin", valid.origin)
        object.__setattr__(malformed, "destination", valid.destination)
        object.__setattr__(malformed, "weekly_loads", 1.5)
        object.__setattr__(malformed, "empty_capacity", valid.empty_capacity)
        object.__setattr__(malformed, "fleet_equipment_share", valid.fleet_equipment_share)
        return replace(result, value=CarrierNetwork(lanes=(malformed,)))


def test_pipeline_produces_reviewable_fit_from_seeded_evidence() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")

    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)

    completed = service.get_run(run.id)
    assert completed.status is RunStatus.AWAITING_REVIEW
    assert completed.output is not None
    assert completed.output.verdict.value == "fit"
    assert completed.output.brief.lanes[0].score.matched_loads_per_week == 31
    assert completed.output.brief.lanes[0].evidence[0].provenance.mode.value == "fixture"
    top_lane = completed.output.brief.lanes[0].score
    assert completed.output.outreach is not None
    assert completed.output.outreach.subject == "A freight conversation for Acme Foods"
    assert "Hi Jordan," in completed.output.outreach.body
    assert f"{top_lane.origin}-to-{top_lane.destination}" in completed.output.outreach.body
    assert completed.output.outreach.body.count("\n\n") == 3


def test_pipeline_returns_needs_more_data_without_lane_evidence() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run(auth_context(rep_id="rep-demo"), "northstar-retail")

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
        run = service.create_run(auth_context(rep_id="rep-demo"), account_id)
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
        run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
        DeterministicProspectPipeline(
            service,
            synthetic_prospect_sources(aliases={"acme-foods": scenario_id}),
        ).run(run.id)
        completed = service.get_run(run.id)
        assert completed.output is not None
        assert completed.output.verdict.value == "needs_more_data"
        assert completed.output.outreach is None


def test_pipeline_abstains_when_source_contains_duplicate_lanes() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    sources = synthetic_prospect_sources()
    sources = replace(sources, network=_DuplicateNetworkSource(sources.network))

    DeterministicProspectPipeline(service, sources).run(run.id)

    completed = service.get_run(run.id)
    assert completed.status is RunStatus.COMPLETED
    assert completed.output is not None
    assert completed.output.verdict.value == "needs_more_data"
    assert completed.output.outreach is None


def test_pipeline_abstains_when_source_contains_malformed_lane_values() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    sources = synthetic_prospect_sources()
    sources = replace(sources, network=_MalformedNetworkSource(sources.network))

    DeterministicProspectPipeline(service, sources).run(run.id)

    completed = service.get_run(run.id)
    assert completed.status is RunStatus.COMPLETED
    assert completed.output is not None
    assert completed.output.verdict.value == "needs_more_data"
    assert completed.output.outreach is None


@pytest.mark.parametrize(
    ("scenario_id", "expected_verdict", "expected_lane_count"),
    (("edge_04", "no_fit", 0), ("edge_07", "fit", 1)),
)
def test_pipeline_verdict_depends_on_direct_capacity_not_equipment_share(
    scenario_id: str,
    expected_verdict: str,
    expected_lane_count: int,
) -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")

    DeterministicProspectPipeline(
        service,
        synthetic_prospect_sources(aliases={"acme-foods": scenario_id}),
    ).run(run.id)

    completed = service.get_run(run.id)
    assert completed.output is not None
    assert completed.output.verdict.value == expected_verdict
    assert len(completed.output.brief.lanes) == expected_lane_count
