"""Numeric-grounding evaluator behavior."""

from typing import cast

from langsmith.evaluation import EvaluationResult

from app.features.prospect_intelligence.public import PROSPECT_FILES
from evaluation.evaluators.numeric_grounding import evaluate_numeric_grounding
from tests.unit.evaluation.support import artifacts, outputs


def _metadata(result: EvaluationResult) -> dict[str, object]:
    return cast(
        "dict[str, object]",
        result.metadata,  # pyright: ignore[reportUnknownMemberType]
    )


def test_numeric_grounding_uses_only_research_and_analysis_evidence() -> None:
    values = artifacts()
    passing = evaluate_numeric_grounding(outputs(values), {})
    values[PROSPECT_FILES.sales_brief] += " Published in 2026."
    failing = evaluate_numeric_grounding(outputs(values), {})

    assert passing.score == 1.0
    assert _metadata(passing)["passed"] is True
    assert failing.score == 0.0
    assert _metadata(failing)["unsupported_values"] == ["2026"]


def test_numeric_grounding_fails_closed_for_malformed_evidence() -> None:
    values = artifacts()
    values[PROSPECT_FILES.freight_research] = "not-json"
    result = evaluate_numeric_grounding(outputs(values), {})

    assert result.score == 0.0
    assert _metadata(result)["invalid_evidence"] == [PROSPECT_FILES.freight_research]
    assert evaluate_numeric_grounding({}, {}).score == 0.0
