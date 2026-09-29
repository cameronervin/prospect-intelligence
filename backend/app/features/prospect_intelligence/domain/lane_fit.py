"""Runtime implementation of ``lane_fit_v1``."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .models import LaneFitResult, NetworkLane, ShipperLane

ZERO = Decimal(0)
ONE = Decimal(1)


def _require_shipper_lane(value: object) -> ShipperLane:
    if not isinstance(value, ShipperLane):
        raise ValueError("malformed shipper lane")
    ShipperLane(
        value.origin,
        value.destination,
        value.weekly_loads,
        value.equipment,
        value.estimated_rate,
        value.distance_miles,
    )
    return value


def _require_network_lane(value: object) -> NetworkLane:
    if not isinstance(value, NetworkLane):
        raise ValueError("malformed network lane")
    NetworkLane(
        value.origin,
        value.destination,
        value.weekly_loads,
        value.empty_capacity,
        value.fleet_equipment_share,
    )
    return value


@dataclass(frozen=True, slots=True)
class LaneFitConfig:
    """Explicit scoring configuration shared by runtime and evaluators."""

    backhaul_weight: Decimal = Decimal("0.50")
    density_weight: Decimal = Decimal("0.30")
    equipment_weight: Decimal = Decimal("0.20")
    density_loads_at_full_score: int = 40

    def __post_init__(self) -> None:
        weights = (self.backhaul_weight, self.density_weight, self.equipment_weight)
        if any(not weight.is_finite() for weight in weights):
            raise ValueError("lane-fit weights must be finite")
        if self.backhaul_weight + self.density_weight + self.equipment_weight != ONE:
            raise ValueError("lane-fit weights must sum to 1")
        if min(weights) < ZERO:
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


def rank_lane_fits(
    shippers: tuple[ShipperLane, ...],
    networks: tuple[NetworkLane, ...],
    config: LaneFitConfig | None = None,
) -> tuple[LaneFitResult, ...]:
    """Return the deterministic top three direct lanes with usable capacity."""

    shipper_keys: set[tuple[str, str]] = set()
    for value in shippers:
        shipper = _require_shipper_lane(value)
        key = (shipper.origin, shipper.destination)
        if key in shipper_keys:
            raise ValueError(f"duplicate shipper lane: {shipper.origin}-{shipper.destination}")
        shipper_keys.add(key)

    network_by_key: dict[tuple[str, str], NetworkLane] = {}
    for value in networks:
        network = _require_network_lane(value)
        key = (network.origin, network.destination)
        if key in network_by_key:
            raise ValueError(f"duplicate network lane: {network.origin}-{network.destination}")
        network_by_key[key] = network

    scored = (
        score_lane(
            shipper,
            network_by_key.get((shipper.origin, shipper.destination)),
            config,
        )
        for shipper in shippers
    )
    matched = (lane for lane in scored if lane.matched_loads_per_week > 0)
    return tuple(
        sorted(
            matched,
            key=lambda lane: (
                -lane.fit_score,
                -lane.matched_loads_per_week,
                lane.origin,
                lane.destination,
            ),
        )[:3]
    )
