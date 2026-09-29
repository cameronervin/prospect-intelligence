"""Top-lane precision evaluator behavior."""

import json

from app.features.prospect_intelligence.public import PROSPECT_FILES
from evaluation.evaluators.lane_precision import evaluate_lane_precision
from tests.unit.evaluation.support import artifacts, outputs


def test_lane_precision_is_reference_aware_and_deduplicates_top_three() -> None:
    values = artifacts()
    analysis = json.loads(values[PROSPECT_FILES.lane_fit_json])
    first, second = analysis["top_lanes"][:2]
    analysis["top_lanes"] = [first, first, second]
    values[PROSPECT_FILES.lane_fit_json] = json.dumps(analysis)
    expected = [
        f"{first['origin']}-{first['destination']}",
        f"{second['origin']}-{second['destination']}",
        "SEA-PDX",
    ]

    result = evaluate_lane_precision(outputs(values), {"expected_top_lanes": expected})

    assert result.score == 2 / 3
    assert evaluate_lane_precision({}, {"expected_top_lanes": []}).score == 0.0
