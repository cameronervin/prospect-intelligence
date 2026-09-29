"""Deterministic freight-prospect examples shared by local and LangSmith runs."""

from dataclasses import dataclass
from typing import Literal

from app.features.prospect_intelligence.public import FitVerdict, RecommendedNextStep

DATASET_VERSION = "freight-prospect-v1"

DatasetSplit = Literal["core", "edge"]


@dataclass(frozen=True, slots=True)
class EvaluationExample:
    """One synthetic example and the minimum deterministic reference output."""

    example_id: str
    split: DatasetSplit
    account_id: str
    account_name: str
    expected_top_lanes: tuple[str, ...]
    expected_verdict: FitVerdict
    expected_next_step: RecommendedNextStep
    known_facts: tuple[str, ...]
    valid_numeric_values: tuple[int | float, ...]
    tags: frozenset[str] = frozenset()
    injection_canary: str | None = None


def _core_example(index: int) -> EvaluationExample:
    origin = ("DAL", "ATL", "CHI", "MEM", "PHX", "LAX", "SEA", "DEN")[index % 8]
    destination = ("ATL", "DAL", "MEM", "CHI", "LAX", "PHX", "DEN", "SEA")[index % 8]
    weekly_loads = 12 + index * 2
    empty_capacity = 20 + index
    next_step = (
        RecommendedNextStep.EXPAND_EXISTING_LANES
        if index % 3 == 0
        else RecommendedNextStep.NEW_LANE_PITCH
    )
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
        expected_verdict=FitVerdict.FIT,
        expected_next_step=next_step,
        known_facts=(
            f"The account moves {weekly_loads} synthetic loads per week.",
            f"The carrier has {empty_capacity} units of modeled empty capacity.",
        ),
        valid_numeric_values=(weekly_loads, empty_capacity, 52),
        tags=frozenset({"planted_lane_overlap"}),
    )


def _edge_examples() -> tuple[EvaluationExample, ...]:
    definitions: tuple[
        tuple[
            str,
            RecommendedNextStep,
            frozenset[str],
            tuple[int | float, ...],
            str | None,
        ],
        ...,
    ] = (
        (
            "No Coverage Foods",
            RecommendedNextStep.NEEDS_MORE_DATA,
            frozenset({"missing_freight_coverage"}),
            (0,),
            None,
        ),
        (
            "Acme Holdings",
            RecommendedNextStep.NEEDS_MORE_DATA,
            frozenset({"ambiguous_entity"}),
            (2,),
            None,
        ),
        (
            "Conflict Manufacturing",
            RecommendedNextStep.NEEDS_MORE_DATA,
            frozenset({"conflicting_sources"}),
            (18, 31),
            None,
        ),
        (
            "Zero Fit Retail",
            RecommendedNextStep.NOT_A_FIT,
            frozenset({"zero_fit"}),
            (0, 14),
            None,
        ),
        (
            "Canary Distribution",
            RecommendedNextStep.NEW_LANE_PITCH,
            frozenset({"prompt_injection"}),
            (24, 30),
            "FREIGHT_CANARY_7F3A",
        ),
        (
            "Sparse Lane Supply",
            RecommendedNextStep.NEEDS_MORE_DATA,
            frozenset({"missing_freight_coverage", "boundary"}),
            (1,),
            None,
        ),
        (
            "Equipment Mismatch Co",
            RecommendedNextStep.NOT_A_FIT,
            frozenset({"zero_fit", "equipment_mismatch"}),
            (22, 0),
            None,
        ),
        (
            "Stale Signal Industries",
            RecommendedNextStep.NEEDS_MORE_DATA,
            frozenset({"stale_source", "dependency_failure"}),
            (365,),
            None,
        ),
    )
    examples: list[EvaluationExample] = []
    for index, (name, next_step, tags, numbers, canary) in enumerate(definitions, start=1):
        verdict = (
            FitVerdict.NEEDS_MORE_DATA
            if next_step is RecommendedNextStep.NEEDS_MORE_DATA
            else FitVerdict.NO_FIT
            if next_step is RecommendedNextStep.NOT_A_FIT
            else FitVerdict.FIT
        )
        examples.append(
            EvaluationExample(
                example_id=f"edge_{index:02d}",
                split="edge",
                account_id=f"syn_edge_{index:02d}",
                account_name=name,
                expected_top_lanes=(
                    ()
                    if verdict in {FitVerdict.NO_FIT, FitVerdict.NEEDS_MORE_DATA}
                    else ("DAL-ATL",)
                ),
                expected_verdict=verdict,
                expected_next_step=next_step,
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
