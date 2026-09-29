"""Tenant-scoped synthetic carrier-network adapter."""

from typing import cast

from ...contracts.models import SourceCoverage, SourceCoverageStatus
from ...contracts.sources import CarrierNetwork, SourceCallContext, SourceResult
from ...fixtures.synthetic.catalog import SyntheticSourceCatalog


class SyntheticCarrierNetworkSource:
    def __init__(self, catalog: SyntheticSourceCatalog) -> None:
        self._catalog = catalog

    def get_network(self, context: SourceCallContext) -> SourceResult[CarrierNetwork]:
        cache_key = "synthetic-carrier-network"
        cached = context.cache.get(cache_key)
        if isinstance(cached, SourceResult):
            return cast(SourceResult[CarrierNetwork], cached)

        result = SourceResult(
            value=CarrierNetwork(lanes=self._catalog.network_lanes()),
            coverage=SourceCoverage(
                source="Carrier network fixture",
                status=SourceCoverageStatus.COMPLETE,
                detail="Tenant-scoped reviewed synthetic carrier network.",
            ),
            evidence=tuple(
                evidence
                for source_scenario in self._catalog.runtime_scenarios
                for evidence in source_scenario.citations
                if evidence.provenance.source == "Carrier network fixture"
            ),
        )
        context.cache.put(cache_key, result)
        return result
