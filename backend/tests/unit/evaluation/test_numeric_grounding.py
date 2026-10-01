"""Numeric-grounding evaluator behavior."""

import json
from typing import cast

import pytest
from langsmith.evaluation import EvaluationResult

from app.features.prospect_intelligence.public import PROSPECT_FILES
from evaluation.evaluators.numeric_grounding import evaluate_numeric_grounding
from tests.unit.evaluation.support import artifacts, outputs


def _metadata(result: EvaluationResult) -> dict[str, object]:
    return cast(
        "dict[str, object]",
        result.metadata,  # pyright: ignore[reportUnknownMemberType]
    )


def test_numeric_grounding_rejects_an_unsupported_bare_year() -> None:
    values = artifacts()
    passing = evaluate_numeric_grounding(outputs(values), {})
    values[PROSPECT_FILES.sales_brief] += " Published in 2026."
    failing = evaluate_numeric_grounding(outputs(values), {})

    assert passing.score == 1.0
    assert _metadata(passing)["passed"] is True
    assert failing.score == 0.0
    assert _metadata(failing)["unsupported_values"] == ["2026"]


def test_numeric_grounding_ignores_iso_dates_datetimes_and_list_markers() -> None:
    values = artifacts()
    freight = cast("dict[str, object]", json.loads(values[PROSPECT_FILES.freight_research]))
    freight["audit_at"] = "2026-09-29 14:30:59.123Z"
    values[PROSPECT_FILES.freight_research] = json.dumps(freight)
    values[PROSPECT_FILES.sales_brief] += (
        "\n1. Published 2026-09-29."
        "\n2) Refreshed 2026-09-29T00:00:00+00:00."
        "\n3. Checked 2026-09-29 14:30:59.123Z against FAF5.7.1."
        "\n4. Evidence ev_2026abcdef0123456789abcd supports the claim."
    )

    result = evaluate_numeric_grounding(outputs(values), {})

    assert result.score == 1.0
    assert _metadata(result)["unsupported_values"] == []


def test_numeric_grounding_accepts_numbers_from_claims_and_context() -> None:
    values = artifacts()
    values[PROSPECT_FILES.freight_research] = json.dumps(
        {
            "rate": 1250,
            "share": 0.25,
            "evidence": [{"claim": "The 2026 plan covers 7654321 annual loads."}],
        }
    )
    values[PROSPECT_FILES.account_context] = json.dumps({"employee_count": "8765432"})
    values[PROSPECT_FILES.sales_brief] += (
        " The 2026 plan covers 7654321 annual loads for 8765432 employees."
    )

    result = evaluate_numeric_grounding(outputs(values), {})

    assert result.score == 1.0
    assert _metadata(result)["unsupported_values"] == []


def test_numeric_grounding_does_not_treat_version_numbers_as_evidence() -> None:
    values = artifacts()
    values[PROSPECT_FILES.freight_research] = json.dumps(
        {
            "rate": 1250,
            "share": 0.25,
            "claim": "The source release is FAF5.7.1.",
        }
    )
    values[PROSPECT_FILES.sales_brief] += " The standalone measure is 7.1."

    result = evaluate_numeric_grounding(outputs(values), {})

    assert result.score == 0.0
    assert _metadata(result)["unsupported_values"] == ["7.1"]


@pytest.mark.parametrize("unsupported", ["USD987654.32", "Q987654.32"])
def test_numeric_grounding_does_not_hide_compact_quantities_as_versions(
    unsupported: str,
) -> None:
    values = artifacts()
    values[PROSPECT_FILES.sales_brief] += f" Unsupported {unsupported}."

    result = evaluate_numeric_grounding(outputs(values), {})

    assert result.score == 0.0
    assert _metadata(result)["unsupported_values"]


def test_numeric_grounding_does_not_use_claim_list_markers_as_evidence() -> None:
    values = artifacts()
    values[PROSPECT_FILES.freight_research] = json.dumps(
        {
            "rate": 1250,
            "share": 0.25,
            "evidence": [{"claim": "987654321. This source is available."}],
        }
    )
    values[PROSPECT_FILES.sales_brief] += " Unsupported quantity 987654321."

    result = evaluate_numeric_grounding(outputs(values), {})

    assert result.score == 0.0
    assert _metadata(result)["unsupported_values"] == ["987654321"]


def test_numeric_grounding_still_checks_quantities_later_on_list_lines() -> None:
    values = artifacts()
    values[PROSPECT_FILES.outreach_draft] += (
        "\n1. Published 2026-09-29 with 987654321 unsupported loads."
    )

    result = evaluate_numeric_grounding(outputs(values), {})

    assert result.score == 0.0
    assert _metadata(result)["unsupported_values"] == ["987654321"]


def test_numeric_grounding_leaves_date_support_to_claim_review() -> None:
    values = artifacts()
    values[PROSPECT_FILES.sales_brief] += " Date labels 2099-01-01 and 2099-99-99."

    result = evaluate_numeric_grounding(outputs(values), {})

    assert result.score == 1.0
    assert _metadata(result)["unsupported_values"] == []


def test_numeric_grounding_does_not_trust_claim_fields_outside_evidence_items() -> None:
    values = artifacts()
    values[PROSPECT_FILES.freight_research] = json.dumps(
        {
            "rate": 1250,
            "share": 0.25,
            "claim": "Unverified forecast is 987654321 loads.",
            "evidence": [],
        }
    )
    values[PROSPECT_FILES.sales_brief] += " Unverified forecast is 987654321 loads."

    result = evaluate_numeric_grounding(outputs(values), {})

    assert result.score == 0.0
    assert _metadata(result)["unsupported_values"] == ["987654321"]


@pytest.mark.parametrize(
    "path",
    [PROSPECT_FILES.account_context, PROSPECT_FILES.freight_research],
)
def test_numeric_grounding_fails_closed_for_malformed_evidence(path: str) -> None:
    values = artifacts()
    values[path] = "not-json"
    result = evaluate_numeric_grounding(outputs(values), {})

    assert result.score == 0.0
    assert _metadata(result)["invalid_evidence"] == [path]
    assert evaluate_numeric_grounding({}, {}).score == 0.0
