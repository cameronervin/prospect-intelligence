"""Synthetic private-source adapters share one reviewed scenario catalog."""

from dataclasses import replace
from uuid import UUID

import pytest

from app.features.prospect_intelligence.contracts.models import SourceCoverageStatus
from app.features.prospect_intelligence.contracts.sources import (
    CarrierNetworkSource,
    CrmSource,
    FreightIntelligenceSource,
    RunSourceCache,
    SourceCallContext,
)
from app.features.prospect_intelligence.fixtures.synthetic import (
    SYNTHETIC_DATASET_SEED,
    generate_synthetic_scenarios,
)
from app.features.prospect_intelligence.fixtures.synthetic.catalog import (
    SyntheticSourceCatalog,
)
from app.features.prospect_intelligence.integrations.carrier_network.synthetic import (
    SyntheticCarrierNetworkSource,
)
from app.features.prospect_intelligence.integrations.carrier_network.tms import (
    TmsCarrierNetworkSource,
)
from app.features.prospect_intelligence.integrations.crm.salesforce import SalesforceCrmSource
from app.features.prospect_intelligence.integrations.crm.synthetic import SyntheticCrmSource
from app.features.prospect_intelligence.integrations.freight_intelligence.genlogs import (
    GenLogsFreightIntelligenceSource,
)
from app.features.prospect_intelligence.integrations.freight_intelligence.synthetic import (
    SyntheticFreightIntelligenceSource,
)


def _context(*, run_suffix: int = 1) -> SourceCallContext:
    run_id = UUID(f"00000000-0000-0000-0000-{run_suffix:012d}")
    return SourceCallContext(
        run_id=run_id,
        tenant_id="tenant-demo",
        rep_id="rep-demo",
        cache=RunSourceCache(run_id, "tenant-demo", "rep-demo"),
    )


def test_catalog_derives_demo_aliases_from_reviewed_core_scenarios() -> None:
    scenarios = generate_synthetic_scenarios(seed=SYNTHETIC_DATASET_SEED)
    catalog = SyntheticSourceCatalog.reviewed(scenarios)

    acme = catalog.scenario_for_account("acme-foods")
    northstar = catalog.scenario_for_account("northstar-retail")

    assert acme is not None and acme.scenario_id == "core_01"
    assert northstar is not None and northstar.scenario_id == "core_03"
    assert acme.shipper_lanes == next(
        scenario.shipper_lanes for scenario in scenarios if scenario.scenario_id == "core_01"
    )
    assert northstar.network_lanes == next(
        scenario.network_lanes for scenario in scenarios if scenario.scenario_id == "core_03"
    )
    assert len(scenarios) == 32
    assert sum(scenario.split == "core" for scenario in scenarios) == 16
    assert sum(scenario.split == "edge" for scenario in scenarios) == 8
    assert sum(scenario.split == "traffic" for scenario in scenarios) == 8
    assert {scenario.scenario_id for scenario in catalog.runtime_scenarios} == {
        "core_01",
        "core_03",
    }


def test_private_source_adapters_are_structural_and_return_normalized_data() -> None:
    catalog = SyntheticSourceCatalog.reviewed()
    crm = SyntheticCrmSource(catalog)
    freight = SyntheticFreightIntelligenceSource(catalog)
    network = SyntheticCarrierNetworkSource(catalog)
    context = _context()

    assert isinstance(crm, CrmSource)
    assert isinstance(freight, FreightIntelligenceSource)
    assert isinstance(network, CarrierNetworkSource)

    account_result = crm.get_account(context, "acme-foods")
    assert account_result.value is not None
    assert account_result.value.id == "acme-foods"
    assert account_result.value.name == "Acme Foods"
    assert account_result.value.industry == "Food distribution"
    assert account_result.value.location == "Dallas, TX"
    assert account_result.value.tenant_id == "tenant-demo"
    assert account_result.coverage.status is SourceCoverageStatus.COMPLETE
    assert {item.provenance.source for item in account_result.evidence} == {"CRM fixture"}
    assert account_result.evidence[0].provenance.endpoint_or_artifact.endswith(
        "fixtures/synthetic/data/demo_account_aliases.json"
    )
    assert account_result.evidence[0].provenance.evidence_location == "$.accounts['acme-foods']"
    northstar = crm.get_account(_context(run_suffix=2), "northstar-retail")
    assert northstar.value is not None
    assert northstar.value.name == "Northstar Retail"
    assert northstar.value.relationship.value == "Customer"
    assert northstar.value.location == "Atlanta, GA"

    freight_result = freight.get_activity(context, account_result.value)
    assert freight_result.value is not None
    assert freight_result.value.account_id == "acme-foods"
    assert freight_result.value.lanes == catalog.scenario_for_account("acme-foods").shipper_lanes  # type: ignore[union-attr]
    assert freight_result.value.facilities
    assert {item.provenance.source for item in freight_result.evidence} == {"GenLogs fixture"}

    network_result = network.get_network(context)
    assert network_result.value is not None
    scenario = catalog.scenario_for_account("acme-foods")
    assert scenario is not None
    assert all(lane in network_result.value.lanes for lane in scenario.network_lanes)
    assert {item.provenance.source for item in network_result.evidence} == {
        "Carrier network fixture"
    }
    assert all(
        "traffic_" not in item.provenance.evidence_location for item in network_result.evidence
    )

    with pytest.raises(ValueError, match="account tenant"):
        freight.get_activity(context, replace(account_result.value, tenant_id="another-tenant"))


def test_unwired_production_shells_preserve_source_protocols_and_fail_closed() -> None:
    catalog = SyntheticSourceCatalog.reviewed()
    context = _context()
    account = SyntheticCrmSource(catalog).get_account(context, "acme-foods").value
    assert account is not None
    crm = SalesforceCrmSource()
    freight = GenLogsFreightIntelligenceSource()
    network = TmsCarrierNetworkSource()

    assert isinstance(crm, CrmSource)
    assert isinstance(freight, FreightIntelligenceSource)
    assert isinstance(network, CarrierNetworkSource)
    with pytest.raises(NotImplementedError, match="production Salesforce CRM integration"):
        crm.get_account(context, account.id)
    with pytest.raises(NotImplementedError, match="production GenLogs integration"):
        freight.get_activity(context, account)
    with pytest.raises(NotImplementedError, match="production carrier-network integration"):
        network.get_network(context)


def test_private_source_results_cache_within_a_run_but_not_across_runs() -> None:
    class CountingCatalog(SyntheticSourceCatalog):
        calls = 0

        def scenario_for_account(self, account_id: str):  # type: ignore[no-untyped-def]
            self.calls += 1
            return super().scenario_for_account(account_id)

    catalog = CountingCatalog.reviewed()
    crm = SyntheticCrmSource(catalog)
    first_context = _context(run_suffix=1)
    second_context = _context(run_suffix=2)

    first = crm.get_account(first_context, "acme-foods")
    repeated = crm.get_account(first_context, "acme-foods")
    second_run = crm.get_account(second_context, "acme-foods")

    assert first is repeated
    assert second_run is not first
    assert catalog.calls == 2


def test_missing_synthetic_account_is_disclosed_and_terminal_result_is_cached() -> None:
    class CountingCatalog(SyntheticSourceCatalog):
        calls = 0

        def scenario_for_account(self, account_id: str):  # type: ignore[no-untyped-def]
            self.calls += 1
            return super().scenario_for_account(account_id)

    catalog = CountingCatalog.reviewed()
    crm = SyntheticCrmSource(catalog)
    context = _context()

    missing = crm.get_account(context, "missing")
    repeated = crm.get_account(context, "missing")

    assert missing is repeated
    assert missing.value is None
    assert missing.coverage.status is SourceCoverageStatus.UNAVAILABLE
    assert missing.coverage.detail == "No reviewed synthetic CRM record exists for this account."
    assert missing.evidence == ()
    assert catalog.calls == 1


def test_degraded_freight_result_is_recomputed_instead_of_cached() -> None:
    class CountingCatalog(SyntheticSourceCatalog):
        calls = 0

        def scenario_for_account(self, account_id: str):  # type: ignore[no-untyped-def]
            self.calls += 1
            return super().scenario_for_account(account_id)

    catalog = CountingCatalog(
        generate_synthetic_scenarios(),
        aliases={"acme-foods": "edge_03"},
    )
    crm = SyntheticCrmSource(catalog)
    freight = SyntheticFreightIntelligenceSource(catalog)
    context = _context()
    account = crm.get_account(context, "acme-foods").value
    assert account is not None
    baseline_calls = catalog.calls

    first = freight.get_activity(context, account)
    second = freight.get_activity(context, account)

    assert first.coverage.status is SourceCoverageStatus.DEGRADED
    assert second == first
    assert second is not first
    assert catalog.calls == baseline_calls + 2
