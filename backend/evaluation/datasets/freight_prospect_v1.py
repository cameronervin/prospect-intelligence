"""Evaluation projection of the shared deterministic prospect scenarios."""

import json
from dataclasses import dataclass
from typing import Literal, cast
from uuid import UUID, uuid5

from langsmith.schemas import Example

from app.features.prospect_intelligence.public import (
    SYNTHETIC_DATASET_SEED,
    SYNTHETIC_DATASET_VERSION,
    Evidence,
    FitVerdict,
    LaneFitResult,
    RecommendedNextStep,
    ScenarioInputPayload,
    SourceCoverage,
    generate_synthetic_scenarios,
    scenario_payload,
)

DATASET_VERSION = SYNTHETIC_DATASET_VERSION
DatasetSplit = Literal["core", "edge"]
_DATASET_NAMESPACE = UUID("36d66a0e-98d0-4cb4-8a1d-47a478d77a5f")
_DATASET_ID = uuid5(_DATASET_NAMESPACE, DATASET_VERSION)


@dataclass(frozen=True, slots=True)
class EvaluationExample:
    """One complete synthetic input and its deterministic reference output."""

    example_id: str
    split: DatasetSplit
    account_id: str
    account_name: str
    input_payload: ScenarioInputPayload
    expected_top_lanes: tuple[str, ...]
    expected_verdict: FitVerdict
    expected_next_step: RecommendedNextStep
    expected_lane_scores: tuple[LaneFitResult, ...]
    known_facts: tuple[str, ...]
    valid_numeric_values: tuple[int | float, ...]
    citations: tuple[Evidence, ...]
    source_coverage: tuple[SourceCoverage, ...]
    tags: frozenset[str] = frozenset()
    injection_canary: str | None = None


def generate_dataset() -> tuple[EvaluationExample, ...]:
    """Project the 24 offline scenarios; traffic cases remain intentionally excluded."""

    return tuple(
        EvaluationExample(
            example_id=scenario.scenario_id,
            split=cast("DatasetSplit", scenario.split),
            account_id=scenario.account.account_id,
            account_name=scenario.account.account_name,
            input_payload=scenario.input_payload(),
            expected_top_lanes=scenario.reference.expected_top_lanes,
            expected_verdict=scenario.reference.expected_verdict,
            expected_next_step=scenario.reference.expected_next_step,
            expected_lane_scores=scenario.reference.expected_lane_scores,
            known_facts=scenario.reference.known_facts,
            valid_numeric_values=scenario.reference.valid_numeric_values,
            citations=scenario.citations,
            source_coverage=scenario.source_coverage,
            tags=scenario.tags,
            injection_canary=scenario.injection_canary,
        )
        for scenario in generate_synthetic_scenarios()
        if scenario.split in {"core", "edge"}
    )


def canonical_dataset_bytes() -> bytes:
    """Serialize the reviewed offline population with canonical JSON formatting."""

    payload = {
        "dataset_version": DATASET_VERSION,
        "seed": SYNTHETIC_DATASET_SEED,
        "examples": [
            scenario_payload(scenario)
            for scenario in generate_synthetic_scenarios()
            if scenario.split in {"core", "edge"}
        ],
    }
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _lane_score_payload(score: LaneFitResult) -> dict[str, object]:
    return {
        "origin": score.origin,
        "destination": score.destination,
        "shipper_loads_per_week": score.shipper_loads_per_week,
        "matched_loads_per_week": score.matched_loads_per_week,
        "backhaul_fill": str(score.backhaul_fill),
        "density": str(score.density),
        "equipment_match": str(score.equipment_match),
        "fit_score": str(score.fit_score),
        "modeled_annual_revenue": str(score.modeled_annual_revenue),
        "deadhead_miles_avoided": score.deadhead_miles_avoided,
        "method_version": score.method_version,
    }


def langsmith_examples() -> tuple[Example, ...]:
    """Build stable, in-memory rows without exposing references to the target."""

    return tuple(
        Example(
            id=uuid5(_DATASET_ID, source.example_id),
            dataset_id=_DATASET_ID,
            inputs={
                "example_id": source.example_id,
                "account_id": source.account_id,
                "account_name": source.account_name,
                "input_payload": source.input_payload,
            },
            outputs={
                "input_payload": source.input_payload,
                "expected_top_lanes": list(source.expected_top_lanes),
                "expected_verdict": source.expected_verdict.value,
                "expected_next_step": source.expected_next_step.value,
                "expected_lane_scores": [
                    _lane_score_payload(score) for score in source.expected_lane_scores
                ],
                "injection_canary": source.injection_canary,
            },
            metadata={
                "dataset_version": DATASET_VERSION,
                "split": source.split,
                "tags": sorted(source.tags),
            },
        )
        for source in generate_dataset()
    )
