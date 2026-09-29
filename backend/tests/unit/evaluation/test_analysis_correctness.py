"""Complete lane-analysis evaluator behavior."""

import json
from typing import cast

from langsmith.evaluation import EvaluationResult

from app.features.prospect_intelligence.public import PROSPECT_FILES
from evaluation.datasets import generate_dataset
from evaluation.evaluators.analysis_correctness import evaluate_analysis_correctness
from tests.unit.evaluation.support import artifacts, lane_artifact, outputs


def _metadata(result: EvaluationResult) -> dict[str, object]:
    return cast(
        "dict[str, object]",
        result.metadata,  # pyright: ignore[reportUnknownMemberType]
    )


def test_analysis_correctness_recalculates_and_checks_every_ranked_field() -> None:
    example = generate_dataset()[0]
    values = artifacts()
    passing = evaluate_analysis_correctness(
        outputs(values), {"input_payload": example.input_payload}
    )
    changed = json.loads(values[PROSPECT_FILES.lane_fit_json])
    changed["top_lanes"][0]["matched_loads_per_week"] += 1
    values[PROSPECT_FILES.lane_fit_json] = json.dumps(changed)
    failing = evaluate_analysis_correctness(
        outputs(values), {"input_payload": example.input_payload}
    )

    assert passing.score == 1.0
    assert _metadata(passing)["passed"] is True
    assert isinstance(failing.score, (int, float)) and failing.score < 1.0
    assert _metadata(failing)["mismatched"]


def test_analysis_correctness_rejects_reordered_missing_extra_and_malformed_lanes() -> None:
    example = generate_dataset()[0]
    baseline = json.loads(lane_artifact())
    candidates = (
        list(reversed(baseline["top_lanes"])),
        baseline["top_lanes"][:-1],
        [*baseline["top_lanes"], baseline["top_lanes"][0]],
    )
    for lanes in candidates:
        values = artifacts()
        values[PROSPECT_FILES.lane_fit_json] = json.dumps({**baseline, "top_lanes": lanes})
        result = evaluate_analysis_correctness(
            outputs(values), {"input_payload": example.input_payload}
        )
        assert isinstance(result.score, (int, float)) and result.score < 1.0
        assert _metadata(result)["passed"] is False
    assert evaluate_analysis_correctness({}, {"input_payload": example.input_payload}).score == 0.0
