"""Python reference implementation of ``lane_fit_v1``."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .models import LaneFitResult, NetworkLane, ShipperLane

ZERO = Decimal(0)
ONE = Decimal(1)


@dataclass(frozen=True, slots=True)
class LaneFitConfig:
    """Explicit scoring configuration shared by runtime and evaluators."""

    backhaul_weight: Decimal = Decimal("0.50")
    density_weight: Decimal = Decimal("0.30")
    equipment_weight: Decimal = Decimal("0.20")
    density_loads_at_full_score: int = 40

    def __post_init__(self) -> None:
        if self.backhaul_weight + self.density_weight + self.equipment_weight != ONE:
            raise ValueError("lane-fit weights must sum to 1")
        if min(self.backhaul_weight, self.density_weight, self.equipment_weight) < ZERO:
            raise ValueError("lane-fit weights cannot be negative")
        if self.density_loads_at_full_score <= 0:
            raise ValueError("density normalization must be positive")


def score_lane(
    shipper: ShipperLane,
    network: NetworkLane | None,
    config: LaneFitConfig | None = None,
) -> LaneFitResult:
    """Score direct O-to-D carrier fit without inferring reverse-lane capacity."""

    settings = config or LaneFitConfig()
    if network is None or (shipper.origin, shipper.destination) != (
        network.origin,
        network.destination,
    ):
        matched = 0
        backhaul_fill = ZERO
        density = ZERO
        equipment_match = ZERO
    else:
        matched = min(shipper.weekly_loads, network.empty_capacity)
        backhaul_fill = (
            Decimal(matched) / Decimal(network.empty_capacity) if network.empty_capacity else ZERO
        )
        density = min(
            Decimal(network.weekly_loads) / Decimal(settings.density_loads_at_full_score),
            ONE,
        )
        equipment_match = network.fleet_equipment_share.get(shipper.equipment, ZERO)

    fit_score = (
        settings.backhaul_weight * backhaul_fill
        + settings.density_weight * density
        + settings.equipment_weight * equipment_match
    ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    annual_revenue = Decimal(matched) * shipper.estimated_rate * Decimal(52)
    avoided_miles = matched * shipper.distance_miles * 52
    return LaneFitResult(
        origin=shipper.origin,
        destination=shipper.destination,
        shipper_loads_per_week=shipper.weekly_loads,
        matched_loads_per_week=matched,
        backhaul_fill=backhaul_fill,
        density=density,
        equipment_match=equipment_match,
        fit_score=fit_score,
        modeled_annual_revenue=annual_revenue,
        deadhead_miles_avoided=avoided_miles,
    )
