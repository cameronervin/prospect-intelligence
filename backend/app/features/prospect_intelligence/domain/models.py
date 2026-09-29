"""Core freight network value objects."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType


def _require_non_empty_text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def _require_non_negative_integer(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if value < 0:
        raise ValueError(f"{field} cannot be negative")


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
        _require_non_empty_text(self.origin, "origin")
        _require_non_empty_text(self.destination, "destination")
        _require_non_empty_text(self.equipment, "equipment")
        _require_non_negative_integer(self.weekly_loads, "weekly loads")
        _require_non_negative_integer(self.distance_miles, "distance miles")
        if not self.estimated_rate.is_finite():
            raise ValueError("estimated rate must be finite")
        if self.estimated_rate < 0:
            raise ValueError("estimated rate cannot be negative")


@dataclass(frozen=True, slots=True)
class NetworkLane:
    """Carrier capacity and density on the same origin-to-destination lane."""

    origin: str
    destination: str
    weekly_loads: int
    empty_capacity: int
    fleet_equipment_share: Mapping[str, Decimal]

    def __post_init__(self) -> None:
        _require_non_empty_text(self.origin, "origin")
        _require_non_empty_text(self.destination, "destination")
        _require_non_negative_integer(self.weekly_loads, "weekly loads")
        _require_non_negative_integer(self.empty_capacity, "empty capacity")
        normalized = dict(self.fleet_equipment_share)
        for equipment in normalized:
            _require_non_empty_text(equipment, "equipment share keys")
        if any(not share.is_finite() for share in normalized.values()):
            raise ValueError("equipment shares must be finite")
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
