"""LangSmith evaluator for the lane-fit verdict."""

import json
from collections.abc import Mapping
from typing import cast

from langsmith.evaluation import EvaluationResult

from app.features.prospect_intelligence.public import PROSPECT_FILES
from evaluation.contracts.snapshot import snapshot_artifacts


def evaluate_verdict_accuracy(
    outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
) -> EvaluationResult:
    artifacts = snapshot_artifacts(outputs)
    try:
        raw = cast(object, json.loads(artifacts.get(PROSPECT_FILES.lane_fit_json, "")))
    except json.JSONDecodeError:
        raw = None
    predicted = ""
    if isinstance(raw, Mapping):
        value = cast("Mapping[str, object]", raw).get("verdict")
        predicted = value if isinstance(value, str) else ""
    expected_value = reference_outputs.get("expected_verdict")
    expected = expected_value if isinstance(expected_value, str) else ""
    passed = bool(artifacts) and bool(expected) and predicted == expected
    return EvaluationResult(
        key="fit_verdict_accuracy",
        score=1.0 if passed else 0.0,
        metadata={"passed": passed, "predicted": predicted, "expected": expected},
    )
