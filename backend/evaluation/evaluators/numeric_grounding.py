"""LangSmith evaluator for numeric claims in model-authored outputs."""

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import cast

from langsmith.evaluation import EvaluationResult

from app.features.prospect_intelligence.public import PROSPECT_FILES
from evaluation.contracts.observations import decimal_value
from evaluation.contracts.snapshot import (
    snapshot_artifacts,
    snapshot_mapping,
    snapshot_observations,
)

_NUMBER = re.compile(r"(?<![\w])[-+]?\$?\d[\d,]*(?:\.\d+)?%?")


def _observed_values(observation: Mapping[str, object]) -> tuple[set[Decimal], list[str]]:
    raw_values = observation.get("values")
    raw_invalid = observation.get("invalid_evidence")
    if (
        not isinstance(raw_values, Sequence)
        or isinstance(raw_values, (str, bytes, bytearray))
        or not isinstance(raw_invalid, Sequence)
        or isinstance(raw_invalid, (str, bytes, bytearray))
    ):
        return set(), ["numeric_evidence_observation"]
    typed_values = cast("Sequence[object]", raw_values)
    if any(not isinstance(raw, str) for raw in typed_values):
        return set(), ["numeric_evidence_observation"]
    try:
        values = {decimal_value(raw) for raw in typed_values}
    except ValueError:
        return set(), ["numeric_evidence_observation"]
    invalid = [item for item in cast("Sequence[object]", raw_invalid) if isinstance(item, str)]
    if len(invalid) != len(cast("Sequence[object]", raw_invalid)):
        return set(), ["numeric_evidence_observation"]
    return values, invalid


def evaluate_numeric_grounding(
    outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
) -> EvaluationResult:
    del reference_outputs
    artifacts = snapshot_artifacts(outputs)
    evidence = snapshot_mapping(snapshot_observations(outputs).get("numeric_evidence"))
    valid, invalid_evidence = _observed_values(evidence)
    rendered = [
        token
        for path in (PROSPECT_FILES.sales_brief, PROSPECT_FILES.outreach_draft)
        for token in _NUMBER.findall(artifacts.get(path, ""))
    ]
    unsupported = [
        token
        for token in rendered
        if decimal_value(token, percentage=token.endswith("%")) not in valid
    ]
    passed = bool(artifacts) and not invalid_evidence and not unsupported
    return EvaluationResult(
        key="numeric_groundedness",
        score=1.0 if passed else 0.0,
        metadata={
            "passed": passed,
            "unsupported_values": unsupported,
            "invalid_evidence": invalid_evidence,
            "checked_count": len(rendered),
        },
    )
