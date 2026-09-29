"""Evaluation projection of the shared deterministic prospect scenarios."""

import json
from dataclasses import dataclass
from typing import Literal, cast

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
