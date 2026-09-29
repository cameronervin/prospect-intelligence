"""Deterministic freight-prospect examples shared by local and LangSmith runs."""

from dataclasses import dataclass
from typing import Literal

DATASET_VERSION = "freight-prospect-v1"

DatasetSplit = Literal["core", "edge"]
FitVerdict = Literal["expand_existing_lanes", "new_lane_pitch", "not_a_fit", "needs_more_data"]


@dataclass(frozen=True, slots=True)
class EvaluationExample:
    """One synthetic example and the minimum deterministic reference output."""

    example_id: str
    split: DatasetSplit
    account_id: str
    account_name: str
    expected_top_lanes: tuple[str, ...]
    expected_verdict: FitVerdict
    known_facts: tuple[str, ...]
    valid_numeric_values: tuple[int | float, ...]
    tags: frozenset[str] = frozenset()
    injection_canary: str | None = None


def _core_example(index: int) -> EvaluationExample:
    origin = ("DAL", "ATL", "CHI", "MEM", "PHX", "LAX", "SEA", "DEN")[index % 8]
    destination = ("ATL", "DAL", "MEM", "CHI", "LAX", "PHX", "DEN", "SEA")[index % 8]
    weekly_loads = 12 + index * 2
    empty_capacity = 20 + index
    verdict: FitVerdict = "expand_existing_lanes" if index % 3 == 0 else "new_lane_pitch"
    return EvaluationExample(
        example_id=f"core_{index + 1:02d}",
        split="core",
        account_id=f"syn_core_{index + 1:02d}",
        account_name=f"Synthetic Shipper {index + 1:02d}",
        expected_top_lanes=(
            f"{origin}-{destination}",
            f"{destination}-{origin}",
            f"{origin}-HOU",
        ),
        expected_verdict=verdict,
        known_facts=(
            f"The account moves {weekly_loads} synthetic loads per week.",
            f"The carrier has {empty_capacity} units of modeled empty capacity.",
        ),
        valid_numeric_values=(weekly_loads, empty_capacity, 52),
        tags=frozenset({"planted_lane_overlap"}),
    )


def _edge_examples() -> tuple[EvaluationExample, ...]:
    definitions: tuple[
        tuple[str, FitVerdict, frozenset[str], tuple[int | float, ...], str | None], ...
    ] = (
        (
            "No Coverage Foods",
            "needs_more_data",
            frozenset({"missing_freight_coverage"}),
            (0,),
            None,
        ),
        ("Acme Holdings", "needs_more_data", frozenset({"ambiguous_entity"}), (2,), None),
        (
            "Conflict Manufacturing",
            "needs_more_data",
            frozenset({"conflicting_sources"}),
            (18, 31),
            None,
        ),
        ("Zero Fit Retail", "not_a_fit", frozenset({"zero_fit"}), (0, 14), None),
        (
            "Canary Distribution",
            "new_lane_pitch",
            frozenset({"prompt_injection"}),
            (24, 30),
            "FREIGHT_CANARY_7F3A",
        ),
        (
            "Sparse Lane Supply",
            "needs_more_data",
            frozenset({"missing_freight_coverage", "boundary"}),
            (1,),
            None,
        ),
        (
            "Equipment Mismatch Co",
            "not_a_fit",
            frozenset({"zero_fit", "equipment_mismatch"}),
            (22, 0),
            None,
        ),
        (
            "Stale Signal Industries",
            "needs_more_data",
            frozenset({"stale_source", "dependency_failure"}),
            (365,),
            None,
        ),
    )
    examples: list[EvaluationExample] = []
    for index, (name, verdict, tags, numbers, canary) in enumerate(definitions, start=1):
        examples.append(
            EvaluationExample(
                example_id=f"edge_{index:02d}",
                split="edge",
                account_id=f"syn_edge_{index:02d}",
                account_name=name,
                expected_top_lanes=(
                    () if verdict in {"not_a_fit", "needs_more_data"} else ("DAL-ATL",)
                ),
                expected_verdict=verdict,
                known_facts=(f"Synthetic edge condition: {', '.join(sorted(tags))}.",),
                valid_numeric_values=numbers,
                tags=tags,
                injection_canary=canary,
            )
        )
    return tuple(examples)


def generate_dataset() -> tuple[EvaluationExample, ...]:
    """Return the immutable v1 dataset without randomness or external calls."""

    return tuple(_core_example(index) for index in range(16)) + _edge_examples()
