"""Deterministic synthetic evaluation dataset tests."""

import hashlib
import json
import math
from pathlib import Path

from app.features.prospect_intelligence.public import FitVerdict, RecommendedNextStep
from evaluation.datasets.freight_prospect_v1 import (
    DATASET_VERSION,
    canonical_dataset_bytes,
    generate_dataset,
)

GOLDEN_DATASET = (
    Path(__file__).parents[3] / "evaluation" / "datasets" / "golden" / "freight_prospect_v1.json"
)


def test_dataset_has_versioned_core_and_edge_splits() -> None:
    first = generate_dataset()
    second = generate_dataset()

    assert first == second
    assert DATASET_VERSION == "freight-prospect-v1"
    assert len(first) == 24
    assert sum(example.split == "core" for example in first) == 16
    assert sum(example.split == "edge" for example in first) == 8
    assert len({example.example_id for example in first}) == len(first)


def test_dataset_generation_is_byte_stable_and_matches_reviewed_golden_file() -> None:
    first = canonical_dataset_bytes()
    second = canonical_dataset_bytes()

    assert first == second
    assert first.endswith(b"\n")
    assert first == GOLDEN_DATASET.read_bytes()
    assert hashlib.sha256(first).hexdigest() == (
        "d5ed38772ba98dd9195295f851b7d548509e826c0a9c2900dc5195a6220f30c8"
    )
    assert json.loads(first)["dataset_version"] == DATASET_VERSION


def test_edge_split_covers_required_failure_and_adversarial_cases() -> None:
    tags = {
        tag for example in generate_dataset() if example.split == "edge" for tag in example.tags
    }

    assert {
        "missing_freight_coverage",
        "ambiguous_entity",
        "conflicting_sources",
        "zero_fit",
        "prompt_injection",
        "boundary",
        "equipment_mismatch",
        "dependency_failure",
    } <= tags


def test_examples_include_reference_outputs_for_code_evaluators() -> None:
    for example in generate_dataset():
        assert example.account_id.startswith("syn_")
        assert example.expected_verdict in set(FitVerdict)
        assert example.expected_next_step in set(RecommendedNextStep)
        assert example.valid_numeric_values
        assert example.known_facts
        assert example.citations
        assert example.source_coverage
        assert example.input_payload["crm"]["account_id"] == example.account_id
        assert set(example.input_payload) == {
            "carrier_network",
            "crm",
            "faf_market",
            "genlogs",
        }
        assert isinstance(example.input_payload["crm"]["account_name"], str)
        assert isinstance(example.input_payload["crm"]["entity_candidates"], list)
        assert isinstance(example.input_payload["genlogs"]["lanes"], list)
        assert isinstance(example.input_payload["genlogs"]["facilities"], list)
        assert isinstance(example.input_payload["carrier_network"]["lanes"], list)
        assert example.input_payload["faf_market"]["release"] == "FAF5.7.1"
        assert example.input_payload["faf_market"]["year"] == 2023
        assert example.input_payload["faf_market"]["lanes"]
        assert all(citation.provenance.evidence_location for citation in example.citations)
        assert all(
            math.isfinite(float(value)) and value >= 0 for value in example.valid_numeric_values
        )
        assert all(
            lane["estimate_label"] == "project-owned synthetic estimate"
            for lane in example.input_payload["faf_market"]["lanes"]
        )


def test_edge_conditions_are_present_in_source_payloads_not_only_tags() -> None:
    examples = {example.example_id: example for example in generate_dataset()}

    assert examples["edge_01"].input_payload["genlogs"]["coverage"] == "unavailable"
    assert len(examples["edge_02"].input_payload["crm"]["entity_candidates"]) == 2
    assert (
        examples["edge_03"].input_payload["genlogs"]["lanes"][0]["weekly_loads"]
        != (examples["edge_03"].input_payload["crm"]["reported_weekly_loads"])
    )
    assert examples["edge_04"].expected_verdict is FitVerdict.NO_FIT
    canary = examples["edge_05"].injection_canary
    assert canary is not None
    assert canary in examples["edge_05"].input_payload["genlogs"]["source_notes"]
    assert examples["edge_06"].input_payload["genlogs"]["lanes"][0]["weekly_loads"] == 1
    assert examples["edge_07"].input_payload["genlogs"]["lanes"][0]["equipment"] == "reefer"
    assert examples["edge_07"].input_payload["carrier_network"]["lanes"][0][
        "fleet_equipment_share"
    ] == {"dry_van": "1.0"}
    assert examples["edge_07"].expected_lane_scores[0].equipment_match == 0
    assert examples["edge_08"].input_payload["genlogs"]["dependency_error"] == ("fixture_timeout")
