"""Synthetic freight-intelligence adapter backed by reviewed feature fixtures."""

from typing import cast

from ...contracts.models import Account, SourceCoverage, SourceCoverageStatus
from ...contracts.sources import Facility, FreightActivity, SourceCallContext, SourceResult
from ...fixtures.synthetic.catalog import SyntheticSourceCatalog


class SyntheticFreightIntelligenceSource:
    def __init__(self, catalog: SyntheticSourceCatalog) -> None:
        self._catalog = catalog

    def get_activity(
        self, context: SourceCallContext, account: Account
    ) -> SourceResult[FreightActivity]:
        if account.tenant_id != context.tenant_id:
            raise ValueError("account tenant must match the source call context")
        cache_key = f"synthetic-freight:{account.id}"
        cached = context.cache.get(cache_key)
        if isinstance(cached, SourceResult):
            return cast(SourceResult[FreightActivity], cached)

        scenario = self._catalog.scenario_for_account(account.id)
        if scenario is None:
            result = SourceResult[FreightActivity](
                value=None,
                coverage=SourceCoverage(
                    source="GenLogs fixture",
                    status=SourceCoverageStatus.UNAVAILABLE,
                    detail="No reviewed synthetic freight record exists for this account.",
                ),
                evidence=(),
            )
        else:
            coverage = next(
                item for item in scenario.source_coverage if item.source == "GenLogs fixture"
            )
            activity = (
                None
                if coverage.status is SourceCoverageStatus.UNAVAILABLE
                else FreightActivity(
                    account_id=account.id,
                    lanes=scenario.shipper_lanes,
                    facilities=tuple(
                        Facility(
                            id=item.facility_id,
                            name=item.name,
                            city=item.city,
                            state=item.state,
                            facility_type=item.facility_type,
                        )
                        for item in scenario.facilities
                    ),
                )
            )
            result = SourceResult(
                value=activity,
                coverage=coverage,
                evidence=tuple(
                    item
                    for item in scenario.citations
                    if item.provenance.source == "GenLogs fixture"
                ),
            )
        if result.coverage.status is not SourceCoverageStatus.DEGRADED:
            context.cache.put(cache_key, result)
        return result
