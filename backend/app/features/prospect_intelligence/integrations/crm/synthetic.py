"""Synthetic CRM adapter backed by reviewed feature fixtures."""

from typing import cast

from ...contracts.models import (
    Account,
    AccountRelationship,
    Evidence,
    Provenance,
    SourceCoverage,
    SourceCoverageStatus,
    SourceMode,
)
from ...contracts.sources import SourceCallContext, SourceResult
from ...fixtures.synthetic.catalog import ACCOUNT_ALIAS_ARTIFACT, SyntheticSourceCatalog
from ...fixtures.synthetic.provenance import RETRIEVED_AT


class SyntheticCrmSource:
    def __init__(self, catalog: SyntheticSourceCatalog) -> None:
        self._catalog = catalog

    def get_account(self, context: SourceCallContext, account_id: str) -> SourceResult[Account]:
        cache_key = f"synthetic-crm:{account_id}"
        cached = context.cache.get(cache_key)
        if isinstance(cached, SourceResult):
            return cast(SourceResult[Account], cached)

        scenario = self._catalog.scenario_for_account(account_id)
        if scenario is None:
            result = SourceResult[Account](
                value=None,
                coverage=SourceCoverage(
                    mode=SourceMode.FIXTURE,
                    source="CRM fixture",
                    status=SourceCoverageStatus.UNAVAILABLE,
                    detail="No reviewed synthetic CRM record exists for this account.",
                ),
                evidence=(),
            )
        else:
            coverage = next(
                item for item in scenario.source_coverage if item.source == "CRM fixture"
            )
            alias = self._catalog.alias_for_account(account_id)
            evidence = (
                (
                    Evidence(
                        claim="Reviewed CRM demo account record",
                        provenance=Provenance(
                            source="CRM fixture",
                            mode=SourceMode.FIXTURE,
                            endpoint_or_artifact=ACCOUNT_ALIAS_ARTIFACT,
                            retrieved_at=RETRIEVED_AT,
                            evidence_location=f"$.accounts['{account_id}']",
                            source_version="freight-prospect-v1",
                        ),
                    ),
                )
                if self._catalog.has_committed_alias(account_id)
                else tuple(
                    item for item in scenario.citations if item.provenance.source == "CRM fixture"
                )
            )
            result = SourceResult(
                value=Account(
                    id=account_id,
                    tenant_id=context.tenant_id,
                    name=alias.name if alias is not None else scenario.account.account_name,
                    relationship=(
                        alias.relationship
                        if alias is not None
                        else AccountRelationship(scenario.account.relationship)
                    ),
                    industry=alias.industry if alias is not None else scenario.account.industry,
                    location=alias.location if alias is not None else scenario.account.headquarters,
                    contact_name=alias.contact_name if alias is not None else "Operations team",
                    contact_role=(
                        alias.contact_role if alias is not None else "Transportation contact"
                    ),
                    fmcsa_usdot_number=(alias.fmcsa_usdot_number if alias is not None else None),
                ),
                coverage=coverage,
                evidence=evidence,
            )
        context.cache.put(cache_key, result)
        return result
