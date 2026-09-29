"""Stable source lineage and region metadata for synthetic scenarios."""

from datetime import UTC, datetime

from ...contracts.models import (
    Evidence,
    Provenance,
    SourceCoverage,
    SourceCoverageStatus,
    SourceMode,
)
from ...integrations.market_data.faf5 import DerivedMarketLane
from .models import SYNTHETIC_DATASET_VERSION, ScenarioSplit

RETRIEVED_AT = datetime(2026, 9, 29, 12, tzinfo=UTC)
REGIONS: dict[str, tuple[str, str, str]] = {
    "041": ("PHX", "Phoenix", "AZ"),
    "061": ("LAX", "Los Angeles", "CA"),
    "081": ("DEN", "Denver", "CO"),
    "131": ("ATL", "Atlanta", "GA"),
    "171": ("CHI", "Chicago", "IL"),
    "471": ("MEM", "Memphis", "TN"),
    "484": ("DAL", "Dallas", "TX"),
    "531": ("SEA", "Seattle", "WA"),
}


def scenario_evidence(
    scenario_id: str,
    *,
    split: ScenarioSplit,
    market: DerivedMarketLane,
    freight_status: SourceCoverageStatus,
    has_lanes: bool,
    has_network: bool,
) -> tuple[Evidence, ...]:
    artifact = (
        "evaluation/datasets/golden/freight_prospect_v1.json"
        if split != "traffic"
        else "generated:freight-prospect-v1"
    )
    root = "examples" if split != "traffic" else "scenarios"
    scenario_path = f"$.{root}[?(@.scenario_id=='{scenario_id}')].inputs"
    freight_claim = (
        "Synthetic observed shipper lanes and facilities"
        if has_lanes
        else "Synthetic freight source is unavailable or has no trusted lane observations"
        if freight_status is SourceCoverageStatus.UNAVAILABLE
        else "Synthetic freight coverage requires resolution before using lane observations"
    )
    network_claim = (
        "Synthetic carrier capacity and density"
        if has_network
        else "Synthetic carrier network has no reviewed matching capacity"
    )
    fixture_sources = (
        ("CRM fixture", f"{scenario_path}.crm", "Synthetic CRM account and relationship record"),
        ("GenLogs fixture", f"{scenario_path}.genlogs", freight_claim),
        ("Carrier network fixture", f"{scenario_path}.carrier_network", network_claim),
    )
    evidence = [
        Evidence(
            claim=claim,
            provenance=Provenance(
                source=source,
                mode=SourceMode.FIXTURE,
                endpoint_or_artifact=artifact,
                retrieved_at=RETRIEVED_AT,
                evidence_location=location,
                source_version=SYNTHETIC_DATASET_VERSION,
            ),
        )
        for source, location, claim in fixture_sources
    ]
    evidence.append(
        Evidence(
            claim="2023 regional truck-market tonnage",
            provenance=Provenance(
                source="BTS/FHWA FAF5.7.1",
                mode=SourceMode.SNAPSHOT,
                endpoint_or_artifact=(
                    "app/features/prospect_intelligence/integrations/market_data/data/"
                    "faf5_7_1_2023_truck_snapshot.csv"
                ),
                retrieved_at=RETRIEVED_AT,
                evidence_location=(
                    f"dms_orig={market.origin_zone},dms_dest={market.destination_zone},dms_mode=1"
                ),
                source_version="FAF5.7.1-2023-final",
            ),
        )
    )
    return tuple(evidence)


def source_coverage(
    freight_status: SourceCoverageStatus = SourceCoverageStatus.COMPLETE,
    *,
    detail: str | None = None,
) -> tuple[SourceCoverage, ...]:
    return (
        SourceCoverage(source="CRM fixture", status=SourceCoverageStatus.COMPLETE),
        SourceCoverage(source="GenLogs fixture", status=freight_status, detail=detail),
        SourceCoverage(source="Carrier network fixture", status=SourceCoverageStatus.COMPLETE),
        SourceCoverage(source="FAF5.7.1 snapshot", status=SourceCoverageStatus.COMPLETE),
    )
