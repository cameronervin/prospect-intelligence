"""Reference behavior for the versioned carrier lane-fit model."""

from decimal import Decimal

import pytest

from app.features.prospect_intelligence.domain.lane_fit import LaneFitConfig, score_lane
from app.features.prospect_intelligence.domain.models import NetworkLane, ShipperLane


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
