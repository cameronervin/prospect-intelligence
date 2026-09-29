"""LangSmith evaluator for the runtime artifact contract."""

from collections.abc import Mapping, Sequence
from typing import cast

from langsmith.evaluation import EvaluationResult

from evaluation.contracts.observations import REQUIRED_ARTIFACTS
from evaluation.contracts.snapshot import snapshot_mapping, snapshot_observations


def evaluate_file_contract(
    outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
) -> EvaluationResult:
    del reference_outputs
    observation = snapshot_mapping(snapshot_observations(outputs).get("file_contract"))
    list_fields = ("missing", "unexpected", "invalid_json", "invalid_schema")
    normalized: dict[str, list[str]] = {}
    malformed = False
    for field in list_fields:
        value = observation.get(field)
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            malformed = True
            normalized[field] = ["artifact_observation"]
            continue
        typed_value = cast("Sequence[object]", value)
        normalized[field] = [item for item in typed_value if isinstance(item, str)]
        malformed = malformed or len(normalized[field]) != len(typed_value)
    expected_count = observation.get("expected_count")
    actual_count = observation.get("actual_count")
    if (
        isinstance(expected_count, bool)
        or not isinstance(expected_count, int)
        or isinstance(actual_count, bool)
        or not isinstance(actual_count, int)
    ):
        malformed, expected_count, actual_count = True, len(REQUIRED_ARTIFACTS), -1
    failures = {failure for field in list_fields for failure in normalized[field]}
    if malformed:
        failures.add("artifact_observation")
    passed = not failures and actual_count == expected_count == len(REQUIRED_ARTIFACTS)
    score = max((len(REQUIRED_ARTIFACTS) - len(failures)) / len(REQUIRED_ARTIFACTS), 0.0)
    return EvaluationResult(
        key="file_contract",
        score=score,
        metadata={
            "passed": passed,
            **normalized,
            "expected_count": expected_count,
            "actual_count": actual_count,
        },
    )
