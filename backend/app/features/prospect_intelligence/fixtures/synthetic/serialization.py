"""Canonical byte serialization for generated scenario artifacts."""

import json

from ...domain.models import LaneFitResult
from .generator import generate_synthetic_scenarios
from .models import SYNTHETIC_DATASET_SEED, SYNTHETIC_DATASET_VERSION, SyntheticScenario


def _score_payload(score: LaneFitResult) -> dict[str, object]:
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


def scenario_payload(scenario: SyntheticScenario) -> dict[str, object]:
    return {
        "scenario_id": scenario.scenario_id,
        "split": scenario.split,
        "tags": sorted(scenario.tags),
        "injection_canary": scenario.injection_canary,
        "inputs": scenario.input_payload(),
        "citations": [
            {
                "claim": item.claim,
                "source": item.provenance.source,
                "mode": item.provenance.mode.value,
                "endpoint_or_artifact": item.provenance.endpoint_or_artifact,
                "retrieved_at": item.provenance.retrieved_at.isoformat(),
                "evidence_location": item.provenance.evidence_location,
                "source_version": item.provenance.source_version,
            }
            for item in scenario.citations
        ],
        "source_coverage": [
            {"source": item.source, "status": item.status.value, "detail": item.detail}
            for item in scenario.source_coverage
        ],
        "reference": {
            "expected_top_lanes": list(scenario.reference.expected_top_lanes),
            "expected_verdict": scenario.reference.expected_verdict.value,
            "expected_next_step": scenario.reference.expected_next_step.value,
            "expected_lane_scores": [
                _score_payload(score) for score in scenario.reference.expected_lane_scores
            ],
            "known_facts": list(scenario.reference.known_facts),
            "valid_numeric_values": list(scenario.reference.valid_numeric_values),
        },
    }


def canonical_scenarios_bytes(*, seed: int = SYNTHETIC_DATASET_SEED) -> bytes:
    payload = {
        "dataset_version": SYNTHETIC_DATASET_VERSION,
        "seed": seed,
        "scenarios": [
            scenario_payload(scenario) for scenario in generate_synthetic_scenarios(seed=seed)
        ],
    }
    return (
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()
