"""Typed records for deterministic synthetic prospect scenarios."""

from dataclasses import dataclass
from typing import Literal, TypedDict

from ...contracts.models import Evidence, FitVerdict, RecommendedNextStep, SourceCoverage
from ...domain.models import LaneFitResult, NetworkLane, ShipperLane
from ...integrations.market_data.faf5 import DerivedMarketLane

SYNTHETIC_DATASET_VERSION = "freight-prospect-v1"
SYNTHETIC_DATASET_SEED = 28_029
ESTIMATE_LABEL = "project-owned synthetic estimate"
ScenarioSplit = Literal["core", "edge", "traffic"]


class CrmInputPayload(TypedDict):
    account_id: str
    account_name: str
    relationship: str
    industry: str
    headquarters: str
    reported_weekly_loads: int | None
    entity_candidates: list[dict[str, str]]


class GenLogsLanePayload(TypedDict):
    origin: str
    destination: str
    weekly_loads: int
    equipment: str
    estimated_rate: str
    distance_miles: int


class FacilityPayload(TypedDict):
    facility_id: str
    name: str
    city: str
    state: str
    facility_type: str


class GenLogsInputPayload(TypedDict):
    source: str
    coverage: str
    lanes: list[GenLogsLanePayload]
    facilities: list[FacilityPayload]
    source_notes: str
    dependency_error: str | None


class CarrierLanePayload(TypedDict):
    origin: str
    destination: str
    weekly_loads: int
    empty_capacity: int
    fleet_equipment_share: dict[str, str]


class CarrierNetworkInputPayload(TypedDict):
    source: str
    lanes: list[CarrierLanePayload]


class FafLanePayload(TypedDict):
    origin_zone: str
    destination_zone: str
    mode: str
    thousand_tons_2023: str
    synthetic_shipper_share: str
    estimated_loads_per_week: int
    estimate_label: str


class FafMarketInputPayload(TypedDict):
    source: str
    release: str
    year: int
    lanes: list[FafLanePayload]


class ScenarioInputPayload(TypedDict):
    crm: CrmInputPayload
    genlogs: GenLogsInputPayload
    carrier_network: CarrierNetworkInputPayload
    faf_market: FafMarketInputPayload


@dataclass(frozen=True, slots=True)
class SyntheticAccount:
    account_id: str
    account_name: str
    relationship: str
    industry: str
    headquarters: str
    reported_weekly_loads: int | None = None
    entity_candidates: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class SyntheticFacility:
    facility_id: str
    name: str
    city: str
    state: str
    facility_type: str


@dataclass(frozen=True, slots=True)
class ScenarioReference:
    expected_top_lanes: tuple[str, ...]
    expected_verdict: FitVerdict
    expected_next_step: RecommendedNextStep
    expected_lane_scores: tuple[LaneFitResult, ...]
    known_facts: tuple[str, ...]
    valid_numeric_values: tuple[int | float, ...]


@dataclass(frozen=True, slots=True)
class SyntheticScenario:
    scenario_id: str
    split: ScenarioSplit
    account: SyntheticAccount
    facilities: tuple[SyntheticFacility, ...]
    shipper_lanes: tuple[ShipperLane, ...]
    network_lanes: tuple[NetworkLane, ...]
    market_lanes: tuple[DerivedMarketLane, ...]
    source_coverage: tuple[SourceCoverage, ...]
    citations: tuple[Evidence, ...]
    reference: ScenarioReference
    tags: frozenset[str] = frozenset()
    source_notes: str = ""
    dependency_error: str | None = None
    injection_canary: str | None = None

    def input_payload(self) -> ScenarioInputPayload:
        coverage = next(item for item in self.source_coverage if item.source == "GenLogs fixture")
        return {
            "crm": {
                "account_id": self.account.account_id,
                "account_name": self.account.account_name,
                "relationship": self.account.relationship,
                "industry": self.account.industry,
                "headquarters": self.account.headquarters,
                "reported_weekly_loads": self.account.reported_weekly_loads,
                "entity_candidates": [
                    {"entity_id": entity_id, "name": name}
                    for entity_id, name in self.account.entity_candidates
                ],
            },
            "genlogs": {
                "source": "synthetic GenLogs-shaped fixture",
                "coverage": coverage.status.value,
                "lanes": [
                    {
                        "origin": lane.origin,
                        "destination": lane.destination,
                        "weekly_loads": lane.weekly_loads,
                        "equipment": lane.equipment,
                        "estimated_rate": str(lane.estimated_rate),
                        "distance_miles": lane.distance_miles,
                    }
                    for lane in self.shipper_lanes
                ],
                "facilities": [
                    {
                        "facility_id": item.facility_id,
                        "name": item.name,
                        "city": item.city,
                        "state": item.state,
                        "facility_type": item.facility_type,
                    }
                    for item in self.facilities
                ],
                "source_notes": self.source_notes,
                "dependency_error": self.dependency_error,
            },
            "carrier_network": {
                "source": "tenant-scoped synthetic carrier network",
                "lanes": [
                    {
                        "origin": lane.origin,
                        "destination": lane.destination,
                        "weekly_loads": lane.weekly_loads,
                        "empty_capacity": lane.empty_capacity,
                        "fleet_equipment_share": {
                            name: str(share)
                            for name, share in sorted(lane.fleet_equipment_share.items())
                        },
                    }
                    for lane in self.network_lanes
                ],
            },
            "faf_market": {
                "source": "BTS/FHWA FAF5.7.1 snapshot",
                "release": "FAF5.7.1",
                "year": 2023,
                "lanes": [
                    {
                        "origin_zone": lane.origin_zone,
                        "destination_zone": lane.destination_zone,
                        "mode": lane.mode,
                        "thousand_tons_2023": str(lane.thousand_tons_2023),
                        "synthetic_shipper_share": str(lane.synthetic_shipper_share),
                        "estimated_loads_per_week": lane.estimated_loads_per_week,
                        "estimate_label": lane.estimate_label,
                    }
                    for lane in self.market_lanes
                ],
            },
        }
