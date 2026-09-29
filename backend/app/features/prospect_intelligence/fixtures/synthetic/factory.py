"""Reusable constructors for complete synthetic scenarios."""

from decimal import Decimal

from ...contracts.models import FitVerdict, RecommendedNextStep, SourceCoverageStatus
from ...domain.lane_fit import rank_lane_fits
from ...domain.models import LaneFitResult, NetworkLane, ShipperLane
from ...integrations.market_data.faf5 import DerivedMarketLane
from .models import (
    ESTIMATE_LABEL,
    ScenarioReference,
    ScenarioSplit,
    SyntheticAccount,
    SyntheticFacility,
    SyntheticScenario,
)
from .provenance import REGIONS, scenario_evidence, source_coverage

INDUSTRIES = ("Food products", "Retail", "Manufacturing", "Consumer goods")


def network_for_lanes(
    lanes: tuple[ShipperLane, ...], *, equipment: str = "dry_van"
) -> tuple[NetworkLane, ...]:
    return tuple(
        NetworkLane(
            origin=lane.origin,
            destination=lane.destination,
            weekly_loads=max(8, 32 - index * 7),
            empty_capacity=max(2, lane.weekly_loads - index),
            fleet_equipment_share={equipment: Decimal("0.90") - Decimal(index) / Decimal(10)},
        )
        for index, lane in enumerate(lanes)
    )


def standard_lanes(market: DerivedMarketLane) -> tuple[ShipperLane, ...]:
    origin = REGIONS[market.origin_zone][0]
    destination = REGIONS[market.destination_zone][0]
    loads = market.estimated_loads_per_week
    return (
        ShipperLane(origin, destination, loads, "dry_van", Decimal("1750"), 780),
        ShipperLane(destination, origin, max(1, loads - 1), "dry_van", Decimal("1650"), 780),
        ShipperLane(origin, "HOU", max(1, loads // 2), "dry_van", Decimal("1400"), 600),
    )


def _scores(
    lanes: tuple[ShipperLane, ...], networks: tuple[NetworkLane, ...]
) -> tuple[LaneFitResult, ...]:
    return rank_lane_fits(lanes, networks)


def _numeric_values(
    lanes: tuple[ShipperLane, ...],
    networks: tuple[NetworkLane, ...],
    market: DerivedMarketLane,
    scores: tuple[LaneFitResult, ...],
    reported_weekly_loads: int | None,
) -> tuple[int | float, ...]:
    values: set[int | float] = {
        20,
        52,
        float(market.thousand_tons_2023),
        float(market.synthetic_shipper_share),
        market.estimated_loads_per_week,
    }
    if reported_weekly_loads is not None:
        values.add(reported_weekly_loads)
    for lane in lanes:
        values.update({lane.weekly_loads, int(lane.estimated_rate), lane.distance_miles})
    for lane in networks:
        values.update({lane.weekly_loads, lane.empty_capacity})
    for score in scores:
        values.update(
            {
                score.matched_loads_per_week,
                float(score.fit_score),
                int(score.modeled_annual_revenue),
                score.deadhead_miles_avoided,
            }
        )
    return tuple(sorted(values, key=lambda value: (float(value), isinstance(value, float))))


def build_scenario(
    *,
    scenario_id: str,
    split: ScenarioSplit,
    account_id: str,
    account_name: str,
    market: DerivedMarketLane,
    lanes: tuple[ShipperLane, ...],
    networks: tuple[NetworkLane, ...],
    verdict: FitVerdict,
    next_step: RecommendedNextStep,
    tags: frozenset[str],
    freight_status: SourceCoverageStatus = SourceCoverageStatus.COMPLETE,
    coverage_detail: str | None = None,
    reported_weekly_loads: int | None = None,
    entity_candidates: tuple[tuple[str, str], ...] = (),
    source_notes: str = "Reviewed deterministic fixture.",
    dependency_error: str | None = None,
    injection_canary: str | None = None,
) -> SyntheticScenario:
    ranked = _scores(lanes, networks)
    expected_scores = ranked[:3] if verdict is FitVerdict.FIT else ()
    origin = REGIONS[market.origin_zone]
    destination = REGIONS[market.destination_zone]
    account = SyntheticAccount(
        account_id=account_id,
        account_name=account_name,
        relationship="Prospect",
        industry=INDUSTRIES[int(scenario_id[-2:]) % len(INDUSTRIES)],
        headquarters=f"{origin[1]}, {origin[2]}",
        reported_weekly_loads=reported_weekly_loads,
        entity_candidates=entity_candidates,
    )
    facilities = (
        SyntheticFacility(
            f"{account_id}-origin",
            f"{account_name} shipping facility",
            origin[1],
            origin[2],
            "distribution_center",
        ),
        SyntheticFacility(
            f"{account_id}-destination",
            f"{account_name} receiving facility",
            destination[1],
            destination[2],
            "warehouse",
        ),
    )
    reference = ScenarioReference(
        expected_top_lanes=tuple(
            f"{score.origin}-{score.destination}" for score in expected_scores
        ),
        expected_verdict=verdict,
        expected_next_step=next_step,
        expected_lane_scores=expected_scores,
        known_facts=(
            f"FAF5.7.1 reports {market.thousand_tons_2023} thousand tons of 2023 truck freight.",
            (
                f"The scenario models {market.estimated_loads_per_week} loads per week as a "
                f"{ESTIMATE_LABEL}."
            ),
        ),
        valid_numeric_values=_numeric_values(
            lanes, networks, market, expected_scores, reported_weekly_loads
        ),
    )
    return SyntheticScenario(
        scenario_id,
        split,
        account,
        facilities,
        lanes,
        networks,
        (market,),
        source_coverage(freight_status, detail=coverage_detail),
        scenario_evidence(
            scenario_id,
            split=split,
            market=market,
            freight_status=freight_status,
            has_lanes=bool(lanes),
            has_network=bool(networks),
        ),
        reference,
        tags,
        source_notes,
        dependency_error,
        injection_canary,
    )
