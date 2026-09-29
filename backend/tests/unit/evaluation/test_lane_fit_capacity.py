"""Focused lane-fit capacity boundaries."""

import pytest

from evaluation.references.lane_fit_v1 import rank_lane_fit


@pytest.mark.parametrize(
    ("shipper_loads", "empty_capacity", "expected_matched"),
    [(1, 8, 1), (8, 8, 8), (9, 8, 8)],
)
def test_reference_matched_loads_are_bounded_by_demand_and_capacity(
    shipper_loads: int, empty_capacity: int, expected_matched: int
) -> None:
    shipper = {
        "origin": "DAL",
        "destination": "ATL",
        "weekly_loads": shipper_loads,
        "equipment": "dry_van",
        "estimated_rate": "1750",
        "distance_miles": 780,
    }
    network = {
        "origin": "DAL",
        "destination": "ATL",
        "weekly_loads": 40,
        "empty_capacity": empty_capacity,
        "fleet_equipment_share": {"dry_van": "0.75"},
    }

    score = rank_lane_fit((shipper,), (network,))[0]

    assert score.matched_loads_per_week == expected_matched
