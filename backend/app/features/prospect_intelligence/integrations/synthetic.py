"""Seeded synthetic freight data with explicit provenance."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from ..contracts.models import Evidence, Provenance, SourceMode
from ..domain.models import NetworkLane, ShipperLane


@dataclass(frozen=True, slots=True)
class SyntheticAccountData:
    account_id: str
    shipper_lanes: tuple[ShipperLane, ...]
    network_lanes: tuple[NetworkLane, ...]
    evidence: tuple[Evidence, ...]


def seeded_source_data() -> tuple[SyntheticAccountData, ...]:
    """Return stable fixtures; timestamps identify the fixture build, not runtime."""

    retrieved_at = datetime(2026, 9, 29, 12, tzinfo=UTC)
    return (
        SyntheticAccountData(
            account_id="acme-foods",
            shipper_lanes=(
                ShipperLane(
                    origin="Atlanta, GA",
                    destination="Dallas, TX",
                    weekly_loads=12,
                    equipment="dry_van",
                    estimated_rate=Decimal("1500"),
                    distance_miles=800,
                ),
            ),
            network_lanes=(
                NetworkLane(
                    origin="Atlanta, GA",
                    destination="Dallas, TX",
                    weekly_loads=24,
                    empty_capacity=8,
                    fleet_equipment_share={"dry_van": Decimal("0.90")},
                ),
            ),
            evidence=(
                Evidence(
                    claim="12 observed loads per week",
                    provenance=Provenance(
                        source="GenLogs fixture",
                        mode=SourceMode.FIXTURE,
                        endpoint_or_artifact="fixtures/genlogs/acme-foods.json",
                        retrieved_at=retrieved_at,
                        evidence_location="$.lanes[0].weekly_loads",
                        source_version="synthetic-v1",
                    ),
                ),
            ),
        ),
    )
