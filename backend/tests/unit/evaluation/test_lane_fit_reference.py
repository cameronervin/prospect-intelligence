"""Independent ``lane_fit_v1`` reference and packaged skill tests."""

import json
from dataclasses import asdict
from decimal import Decimal
from importlib.resources import files
from pathlib import Path

import pytest

from evaluation.datasets.freight_prospect_v1 import generate_dataset
from evaluation.references.lane_fit_v1 import (
    ReferenceLaneScore,
    evaluate_lane_fit,
    rank_lane_fit,
)

GOLDEN_DATASET = (
    Path(__file__).parents[3] / "evaluation" / "datasets" / "golden" / "freight_prospect_v1.json"
)


def _shipper(
    origin: str = "DAL",
    destination: str = "ATL",
    *,
    weekly_loads: object = 10,
) -> dict[str, object]:
    return {
        "origin": origin,
        "destination": destination,
        "weekly_loads": weekly_loads,
        "equipment": "dry_van",
        "estimated_rate": "1750",
        "distance_miles": 780,
    }


def _network(
    origin: str = "DAL",
    destination: str = "ATL",
    *,
    weekly_loads: object = 40,
    empty_capacity: object = 8,
) -> dict[str, object]:
    return {
        "origin": origin,
        "destination": destination,
        "weekly_loads": weekly_loads,
        "empty_capacity": empty_capacity,
        "fleet_equipment_share": {"dry_van": "0.75"},
    }


def test_reference_scores_raw_mappings_at_capacity_and_density_boundaries() -> None:
    score = rank_lane_fit((_shipper(),), (_network(),))[0]

    assert score == ReferenceLaneScore(
        origin="DAL",
        destination="ATL",
        shipper_loads_per_week=10,
        matched_loads_per_week=8,
        backhaul_fill=Decimal("1"),
        density=Decimal("1"),
        equipment_match=Decimal("0.75"),
        fit_score=Decimal("0.9500"),
        modeled_annual_revenue=Decimal("728000"),
        deadhead_miles_avoided=324_480,
    )


def test_reference_excludes_reverse_and_zero_capacity_lanes() -> None:
    assert rank_lane_fit((_shipper(),), (_network("ATL", "DAL"),)) == ()
    assert rank_lane_fit((_shipper(),), (_network(empty_capacity=0),)) == ()


def test_reference_rejects_duplicate_routes_and_malformed_non_finite_values() -> None:
    duplicate = (_network(), _network(weekly_loads=20))
    invalid = _shipper(weekly_loads="NaN")

    duplicate_result = evaluate_lane_fit(
        {
            "genlogs": {"coverage": "complete", "lanes": [_shipper()]},
            "carrier_network": {"lanes": list(duplicate)},
            "crm": {"entity_candidates": []},
        }
    )
    invalid_result = evaluate_lane_fit(
        {
            "genlogs": {"coverage": "complete", "lanes": [invalid]},
            "carrier_network": {"lanes": [_network()]},
            "crm": {"entity_candidates": []},
        }
    )

    assert duplicate_result.verdict == "needs_more_data"
    assert duplicate_result.lanes == ()
    assert invalid_result.verdict == "needs_more_data"
    assert invalid_result.lanes == ()


def test_reference_rejects_malformed_unmatched_network_evidence() -> None:
    malformed_network = _network("SEA", "DEN", weekly_loads="Infinity")

    result = evaluate_lane_fit(
        {
            "genlogs": {"coverage": "complete", "lanes": [_shipper()]},
            "carrier_network": {"lanes": [malformed_network]},
            "crm": {"entity_candidates": []},
        }
    )

    assert result.verdict == "needs_more_data"
    assert result.lanes == ()


@pytest.mark.parametrize("value", (1.0, "1"))
@pytest.mark.parametrize(
    ("record_name", "field"),
    (
        ("shipper", "weekly_loads"),
        ("shipper", "distance_miles"),
        ("network", "weekly_loads"),
        ("network", "empty_capacity"),
    ),
)
def test_reference_requires_actual_integer_count_types(
    value: object,
    record_name: str,
    field: str,
) -> None:
    shipper = _shipper()
    network = _network()
    record = shipper if record_name == "shipper" else network
    record[field] = value

    result = evaluate_lane_fit(
        {
            "genlogs": {"coverage": "complete", "lanes": [shipper]},
            "carrier_network": {"lanes": [network]},
            "crm": {"entity_candidates": []},
        }
    )

    assert result.verdict == "needs_more_data"
    assert result.lanes == ()


def test_reference_matches_all_reviewed_fixture_outputs() -> None:
    for example in generate_dataset():
        actual = evaluate_lane_fit(example.input_payload)

        assert actual.verdict == example.expected_verdict.value, example.example_id
        assert tuple(f"{lane.origin}-{lane.destination}" for lane in actual.lanes) == (
            example.expected_top_lanes
        ), example.example_id
        assert [asdict(lane) for lane in actual.lanes] == [
            {
                "origin": expected.origin,
                "destination": expected.destination,
                "shipper_loads_per_week": expected.shipper_loads_per_week,
                "matched_loads_per_week": expected.matched_loads_per_week,
                "backhaul_fill": expected.backhaul_fill,
                "density": expected.density,
                "equipment_match": expected.equipment_match,
                "fit_score": expected.fit_score,
                "modeled_annual_revenue": expected.modeled_annual_revenue,
                "deadhead_miles_avoided": expected.deadhead_miles_avoided,
            }
            for expected in example.expected_lane_scores
        ], example.example_id


def test_reference_matches_reviewed_golden_without_runtime_fixture_generation() -> None:
    golden = json.loads(GOLDEN_DATASET.read_text())

    for example in golden["examples"]:
        actual = evaluate_lane_fit(example["inputs"])
        reference = example["reference"]
        actual_scores = [
            {
                "origin": lane.origin,
                "destination": lane.destination,
                "shipper_loads_per_week": lane.shipper_loads_per_week,
                "matched_loads_per_week": lane.matched_loads_per_week,
                "backhaul_fill": str(lane.backhaul_fill),
                "density": str(lane.density),
                "equipment_match": str(lane.equipment_match),
                "fit_score": str(lane.fit_score),
                "modeled_annual_revenue": str(lane.modeled_annual_revenue),
                "deadhead_miles_avoided": lane.deadhead_miles_avoided,
                "method_version": "lane_fit_v1",
            }
            for lane in actual.lanes
        ]

        assert actual.verdict == reference["expected_verdict"], example["scenario_id"]
        assert actual_scores == reference["expected_lane_scores"], example["scenario_id"]


def test_skill_config_is_machine_readable_and_matches_reference_policy() -> None:
    skill_root = (
        Path(str(files("app.features.prospect_intelligence.agents"))) / "skills" / "lane-fit-v1"
    )
    config = json.loads((skill_root / "references" / "config.json").read_text())

    assert (skill_root / "SKILL.md").is_file()
    assert config["method_version"] == "lane_fit_v1"
    assert config["matching"] == "exact_same_direction_origin_destination"
    assert config["weights"] == {
        "backhaul_fill": "0.50",
        "density": "0.30",
        "equipment": "0.20",
    }
    assert config["density_loads_at_full_score"] == 40
    assert config["score_quantum"] == "0.0001"
    assert config["rounding"] == "ROUND_HALF_UP"
    assert config["fit_threshold"] == {"matched_loads_per_week": 1}
    assert config["ranking"] == {
        "limit": 3,
        "eligible": "matched_loads_per_week >= 1",
        "order": [
            "fit_score desc",
            "matched_loads_per_week desc",
            "origin asc",
            "destination asc",
        ],
    }
    assert config["modeled_estimates"] == {
        "annual_weeks": 52,
        "gross_revenue": "matched_loads * estimated_rate * 52",
        "deadhead_displacement": "matched_loads * full_origin_destination_miles * 52",
    }
    assert set(config["verdicts"]) == {"fit", "no_fit", "needs_more_data"}
    assert config["output_labels"] == {
        "deadhead_miles_avoided": "Modeled deadhead avoided",
        "modeled_annual_revenue": "Modeled gross revenue",
    }
    assert set(config["outreach_exclusions"]) == {
        "internal rates",
        "margin",
        "network capacity",
        "deadhead calculations",
        "restricted provider data",
    }
