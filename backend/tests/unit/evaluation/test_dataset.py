"""Deterministic synthetic evaluation dataset tests."""

from app.features.prospect_intelligence.public import FitVerdict, RecommendedNextStep
from evaluation.datasets.freight_prospect_v1 import DATASET_VERSION, generate_dataset


def test_dataset_has_versioned_core_and_edge_splits() -> None:
    first = generate_dataset()
    second = generate_dataset()

    assert first == second
    assert DATASET_VERSION == "freight-prospect-v1"
    assert len(first) == 24
    assert sum(example.split == "core" for example in first) == 16
    assert sum(example.split == "edge" for example in first) == 8
    assert len({example.example_id for example in first}) == len(first)


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
    } <= tags


def test_examples_include_reference_outputs_for_code_evaluators() -> None:
    for example in generate_dataset():
        assert example.account_id.startswith("syn_")
        assert example.expected_verdict in set(FitVerdict)
        assert example.expected_next_step in set(RecommendedNextStep)
        assert example.valid_numeric_values
        assert example.known_facts
