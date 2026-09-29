"""Core freight network value objects."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class ShipperLane:
    """Observed shipper demand on an origin-to-destination lane."""

    origin: str
    destination: str
    weekly_loads: int
    equipment: str
    estimated_rate: Decimal
    distance_miles: int

    def __post_init__(self) -> None:
        if self.weekly_loads < 0 or self.estimated_rate < 0 or self.distance_miles < 0:
            raise ValueError("lane demand, rate, and distance cannot be negative")


@dataclass(frozen=True, slots=True)
class NetworkLane:
    """Carrier capacity and density on the same origin-to-destination lane."""

    origin: str
    destination: str
    weekly_loads: int
    empty_capacity: int
    fleet_equipment_share: Mapping[str, Decimal]

    def __post_init__(self) -> None:
        if self.weekly_loads < 0 or self.empty_capacity < 0:
            raise ValueError("network loads and empty capacity cannot be negative")
        normalized = dict(self.fleet_equipment_share)
        if any(share < 0 or share > 1 for share in normalized.values()):
            raise ValueError("equipment shares must be between 0 and 1")
        object.__setattr__(self, "fleet_equipment_share", MappingProxyType(normalized))


@dataclass(frozen=True, slots=True)
class LaneFitResult:
    """Versioned, deterministic result used by the product and evaluators."""

    origin: str
    destination: str
    shipper_loads_per_week: int
    matched_loads_per_week: int
    backhaul_fill: Decimal
    density: Decimal
    equipment_match: Decimal
    fit_score: Decimal
    modeled_annual_revenue: Decimal
    deadhead_miles_avoided: int
    method_version: str = "lane_fit_v1"
