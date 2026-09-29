"""Reference behavior for the versioned carrier lane-fit model."""

from decimal import Decimal
from itertools import permutations
from typing import cast

import pytest

from app.features.prospect_intelligence.domain.lane_fit import (
    LaneFitConfig,
    rank_lane_fits,
    score_lane,
)
from app.features.prospect_intelligence.domain.models import NetworkLane, ShipperLane
from app.features.prospect_intelligence.public import rank_lane_fits as public_rank_lane_fits


def test_lane_fit_v1_matches_capacity_and_calculates_business_outcomes() -> None:
    shipper = ShipperLane(
        origin="ATL",
        destination="DAL",
        weekly_loads=10,
        equipment="dry_van",
        estimated_rate=Decimal("1500"),
        distance_miles=800,
    )
    network = NetworkLane(
        origin="ATL",
        destination="DAL",
        weekly_loads=20,
        empty_capacity=8,
        fleet_equipment_share={"dry_van": Decimal("0.75")},
    )

    result = score_lane(shipper, network, LaneFitConfig(density_loads_at_full_score=40))

    assert result.method_version == "lane_fit_v1"
    assert result.matched_loads_per_week == 8
    assert result.backhaul_fill == Decimal("1")
    assert result.density == Decimal("0.5")
    assert result.equipment_match == Decimal("0.75")
    assert result.fit_score == Decimal("0.8000")
    assert Decimal(0) <= result.fit_score <= Decimal(1)
    assert result.modeled_annual_revenue == Decimal("624000")
    assert result.deadhead_miles_avoided == 332_800


def test_lane_fit_v1_scores_missing_network_lane_as_zero_fit() -> None:
    shipper = ShipperLane(
        origin="ATL",
        destination="DAL",
        weekly_loads=10,
        equipment="dry_van",
        estimated_rate=Decimal("1500"),
        distance_miles=800,
    )

    result = score_lane(shipper, None)

    assert result.matched_loads_per_week == 0
    assert result.fit_score == Decimal("0.0000")
    assert result.modeled_annual_revenue == Decimal("0")


def test_lane_fit_config_requires_normalized_weights() -> None:
    with pytest.raises(ValueError, match="sum to 1"):
        LaneFitConfig(backhaul_weight=Decimal("0.6"))


def test_lane_fit_v1_requires_exact_direction_and_positive_capacity() -> None:
    shipper = ShipperLane("ATL", "DAL", 10, "dry_van", Decimal("1500"), 800)
    reverse = NetworkLane("DAL", "ATL", 20, 8, {"dry_van": Decimal("0.75")})
    zero_capacity = NetworkLane("ATL", "DAL", 40, 0, {"dry_van": Decimal("1")})

    assert score_lane(shipper, reverse).matched_loads_per_week == 0
    assert score_lane(shipper, zero_capacity).backhaul_fill == Decimal("0")


def test_lane_fit_v1_caps_density_and_rounds_half_up_to_four_places() -> None:
    shipper = ShipperLane("ATL", "DAL", 1, "dry_van", Decimal("1"), 1)
    network = NetworkLane(
        "ATL",
        "DAL",
        41,
        0,
        {"dry_van": Decimal("0.00025")},
    )

    result = score_lane(shipper, network)

    assert result.density == Decimal("1")
    assert result.equipment_match == Decimal("0.00025")
    assert result.fit_score == Decimal("0.3001")
    assert Decimal(0) <= result.fit_score <= Decimal(1)


def test_rank_lane_fits_returns_matched_top_three_with_deterministic_ties() -> None:
    shippers = (
        ShipperLane("CHI", "MEM", 2, "dry_van", Decimal("100"), 10),
        ShipperLane("ATL", "DAL", 2, "dry_van", Decimal("100"), 10),
        ShipperLane("BOS", "MIA", 3, "dry_van", Decimal("100"), 10),
        ShipperLane("DEN", "SEA", 2, "dry_van", Decimal("100"), 10),
        ShipperLane("LAX", "PHX", 2, "dry_van", Decimal("100"), 10),
    )
    networks = (
        NetworkLane("LAX", "PHX", 40, 0, {"dry_van": Decimal("1")}),
        NetworkLane("DEN", "SEA", 40, 2, {"dry_van": Decimal("1")}),
        NetworkLane("BOS", "MIA", 40, 3, {"dry_van": Decimal("1")}),
        NetworkLane("ATL", "DAL", 40, 2, {"dry_van": Decimal("1")}),
        NetworkLane("CHI", "MEM", 40, 2, {"dry_van": Decimal("1")}),
    )

    expected = [("BOS", "MIA"), ("ATL", "DAL"), ("CHI", "MEM")]
    for shipper_order in permutations(shippers[:4]):
        for network_order in permutations(networks[1:]):
            ranked = rank_lane_fits(shipper_order, network_order)

            assert [(lane.origin, lane.destination) for lane in ranked] == expected
            assert all(lane.matched_loads_per_week > 0 for lane in ranked)
            assert all(Decimal(0) <= lane.fit_score <= Decimal(1) for lane in ranked)


@pytest.mark.parametrize("duplicate_source", ("shipper", "network"))
def test_rank_lane_fits_rejects_duplicate_origin_destination_records(
    duplicate_source: str,
) -> None:
    shipper = ShipperLane("ATL", "DAL", 2, "dry_van", Decimal("100"), 10)
    network = NetworkLane("ATL", "DAL", 40, 2, {"dry_van": Decimal("1")})
    shippers = (shipper, shipper) if duplicate_source == "shipper" else (shipper,)
    networks = (network, network) if duplicate_source == "network" else (network,)

    with pytest.raises(ValueError, match=r"duplicate .* lane"):
        rank_lane_fits(shippers, networks)


@pytest.mark.parametrize("value", (Decimal("NaN"), Decimal("Infinity")))
def test_lane_models_reject_non_finite_decimal_inputs(value: Decimal) -> None:
    with pytest.raises(ValueError, match="finite"):
        ShipperLane("ATL", "DAL", 2, "dry_van", value, 10)
    with pytest.raises(ValueError, match="finite"):
        NetworkLane("ATL", "DAL", 40, 2, {"dry_van": value})


def test_rank_lane_fits_rejects_malformed_source_records() -> None:
    with pytest.raises(ValueError, match="malformed shipper"):
        rank_lane_fits((cast(ShipperLane, object()),), ())
    with pytest.raises(ValueError, match="malformed network"):
        rank_lane_fits((), (cast(NetworkLane, object()),))


@pytest.mark.parametrize("field", ("origin", "destination", "equipment"))
def test_shipper_lane_rejects_blank_identifiers(field: str) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        ShipperLane(
            "  " if field == "origin" else "ATL",
            "  " if field == "destination" else "DAL",
            2,
            "  " if field == "equipment" else "dry_van",
            Decimal("100"),
            10,
        )


@pytest.mark.parametrize("field", ("origin", "destination"))
def test_network_lane_rejects_blank_identifiers(field: str) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        NetworkLane(
            "  " if field == "origin" else "ATL",
            "  " if field == "destination" else "DAL",
            40,
            2,
            {"dry_van": Decimal("1")},
        )


@pytest.mark.parametrize("value", (True, 1.5))
def test_lane_models_reject_bool_and_non_integral_counts(value: object) -> None:
    invalid = cast(int, value)
    with pytest.raises(ValueError, match="integer"):
        ShipperLane("ATL", "DAL", invalid, "dry_van", Decimal("100"), 10)
    with pytest.raises(ValueError, match="integer"):
        ShipperLane("ATL", "DAL", 2, "dry_van", Decimal("100"), invalid)
    with pytest.raises(ValueError, match="integer"):
        NetworkLane("ATL", "DAL", invalid, 2, {"dry_van": Decimal("1")})
    with pytest.raises(ValueError, match="integer"):
        NetworkLane("ATL", "DAL", 40, invalid, {"dry_van": Decimal("1")})


def test_network_lane_rejects_blank_equipment_share_keys() -> None:
    with pytest.raises(ValueError, match=r"equipment.*non-empty"):
        NetworkLane("ATL", "DAL", 40, 2, {" ": Decimal("1")})


def test_application_lane_scorer_is_available_through_the_public_boundary() -> None:
    assert public_rank_lane_fits is rank_lane_fits
