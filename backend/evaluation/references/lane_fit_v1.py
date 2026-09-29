"""Independent standard-library reference for the ``lane_fit_v1`` policy.

This module deliberately accepts raw mappings and does not import the application scorer,
configuration, contracts, or fixture builders. It is a test oracle, not a runtime dependency.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal, cast

ZERO = Decimal(0)
ONE = Decimal(1)
BACKHAUL_WEIGHT = Decimal("0.50")
DENSITY_WEIGHT = Decimal("0.30")
EQUIPMENT_WEIGHT = Decimal("0.20")
DENSITY_LOADS_AT_FULL_SCORE = 40
ANNUAL_WEEKS = 52
SCORE_QUANTUM = Decimal("0.0001")


class ReferenceInputError(ValueError):
    """Raised when raw lane evidence cannot be evaluated unambiguously."""


@dataclass(frozen=True, slots=True)
class ReferenceLaneScore:
    """One independently calculated, directly matched lane score."""

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


@dataclass(frozen=True, slots=True)
class LaneFitReferenceResult:
    """Authoritative v1 verdict and ranked, matched lanes."""

    verdict: Literal["fit", "no_fit", "needs_more_data"]
    lanes: tuple[ReferenceLaneScore, ...]


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ReferenceInputError(f"{field} must be an object")
    return cast("Mapping[str, object]", value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ReferenceInputError(f"{field} must be an array")
    return cast("Sequence[object]", value)


def _text(record: Mapping[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ReferenceInputError(f"{field} must be a non-empty string")
    return value


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, float, str)):
        raise ReferenceInputError(f"{field} must be numeric")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as error:
        raise ReferenceInputError(f"{field} must be numeric") from error
    if not parsed.is_finite():
        raise ReferenceInputError(f"{field} must be finite")
    return parsed


def _non_negative_decimal(record: Mapping[str, object], field: str) -> Decimal:
    value = _decimal(record.get(field), field)
    if value < ZERO:
        raise ReferenceInputError(f"{field} cannot be negative")
    return value


def _non_negative_int(record: Mapping[str, object], field: str) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReferenceInputError(f"{field} must be an integer")
    if value < 0:
        raise ReferenceInputError(f"{field} cannot be negative")
    return value


def _lane_key(record: Mapping[str, object]) -> tuple[str, str]:
    return (_text(record, "origin"), _text(record, "destination"))


def _validated_lanes(value: object, field: str) -> tuple[Mapping[str, object], ...]:
    lanes = tuple(_mapping(item, f"{field}[]") for item in _sequence(value, field))
    keys = [_lane_key(lane) for lane in lanes]
    if len(keys) != len(set(keys)):
        raise ReferenceInputError(f"{field} contains duplicate origin-destination lanes")
    return lanes


def _equipment_share(network: Mapping[str, object], equipment: str) -> Decimal:
    shares = _mapping(network.get("fleet_equipment_share"), "fleet_equipment_share")
    if equipment not in shares:
        return ZERO
    share = _decimal(shares[equipment], f"fleet_equipment_share.{equipment}")
    if not ZERO <= share <= ONE:
        raise ReferenceInputError("equipment shares must be between 0 and 1")
    return share


def _validate_shipper(shipper: Mapping[str, object]) -> None:
    _lane_key(shipper)
    _non_negative_int(shipper, "weekly_loads")
    _text(shipper, "equipment")
    _non_negative_decimal(shipper, "estimated_rate")
    _non_negative_int(shipper, "distance_miles")


def _validate_network(network: Mapping[str, object]) -> None:
    _lane_key(network)
    _non_negative_int(network, "weekly_loads")
    _non_negative_int(network, "empty_capacity")
    shares = _mapping(network.get("fleet_equipment_share"), "fleet_equipment_share")
    raw_shares = cast("Mapping[object, object]", shares)
    if any(not isinstance(equipment, str) or not equipment.strip() for equipment in raw_shares):
        raise ReferenceInputError("equipment share keys must be non-empty strings")
    for equipment in shares:
        _equipment_share(network, equipment)


def _score(
    shipper: Mapping[str, object], network: Mapping[str, object]
) -> ReferenceLaneScore | None:
    origin, destination = _lane_key(shipper)
    shipper_loads = _non_negative_int(shipper, "weekly_loads")
    equipment = _text(shipper, "equipment")
    estimated_rate = _non_negative_decimal(shipper, "estimated_rate")
    distance_miles = _non_negative_int(shipper, "distance_miles")

    network_loads = _non_negative_int(network, "weekly_loads")
    empty_capacity = _non_negative_int(network, "empty_capacity")
    equipment_match = _equipment_share(network, equipment)
    matched = min(shipper_loads, empty_capacity)
    if matched < 1:
        return None

    backhaul_fill = Decimal(matched) / Decimal(empty_capacity)
    density = min(Decimal(network_loads) / Decimal(DENSITY_LOADS_AT_FULL_SCORE), ONE)
    fit_score = (
        BACKHAUL_WEIGHT * backhaul_fill
        + DENSITY_WEIGHT * density
        + EQUIPMENT_WEIGHT * equipment_match
    ).quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)
    return ReferenceLaneScore(
        origin=origin,
        destination=destination,
        shipper_loads_per_week=shipper_loads,
        matched_loads_per_week=matched,
        backhaul_fill=backhaul_fill,
        density=density,
        equipment_match=equipment_match,
        fit_score=fit_score,
        modeled_annual_revenue=Decimal(matched) * estimated_rate * Decimal(ANNUAL_WEEKS),
        deadhead_miles_avoided=matched * distance_miles * ANNUAL_WEEKS,
    )


def rank_lane_fit(
    shipper_lanes: Sequence[Mapping[str, object]],
    network_lanes: Sequence[Mapping[str, object]],
) -> tuple[ReferenceLaneScore, ...]:
    """Validate, independently score, and deterministically rank direct matches."""

    shippers = _validated_lanes(shipper_lanes, "shipper_lanes")
    networks = _validated_lanes(network_lanes, "network_lanes")
    for shipper in shippers:
        _validate_shipper(shipper)
    for network in networks:
        _validate_network(network)
    network_by_lane = {_lane_key(lane): lane for lane in networks}
    scored: list[ReferenceLaneScore] = []
    for shipper in shippers:
        network = network_by_lane.get(_lane_key(shipper))
        if network is None:
            continue
        score = _score(shipper, network)
        if score is not None:
            scored.append(score)
    return tuple(
        sorted(
            scored,
            key=lambda lane: (
                -lane.fit_score,
                -lane.matched_loads_per_week,
                lane.origin,
                lane.destination,
            ),
        )[:3]
    )


def evaluate_lane_fit(payload: Mapping[str, object]) -> LaneFitReferenceResult:
    """Evaluate a raw source payload, converting unusable evidence to a safe verdict."""

    try:
        crm = _mapping(payload.get("crm"), "crm")
        freight = _mapping(payload.get("genlogs"), "genlogs")
        network = _mapping(payload.get("carrier_network"), "carrier_network")
        candidates = _sequence(crm.get("entity_candidates", ()), "crm.entity_candidates")
        coverage = freight.get("coverage")
        dependency_error = freight.get("dependency_error")
        if coverage != "complete" or dependency_error is not None or len(candidates) > 1:
            return LaneFitReferenceResult("needs_more_data", ())
        shipper_lanes = _validated_lanes(freight.get("lanes"), "genlogs.lanes")
        if not shipper_lanes:
            return LaneFitReferenceResult("needs_more_data", ())
        network_lanes = _validated_lanes(network.get("lanes"), "carrier_network.lanes")
        ranked = rank_lane_fit(shipper_lanes, network_lanes)
    except (ReferenceInputError, ArithmeticError):
        return LaneFitReferenceResult("needs_more_data", ())
    return LaneFitReferenceResult("fit" if ranked else "no_fit", ranked)
