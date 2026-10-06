"""Runtime file-contract evaluator behavior."""

import json
from typing import cast

from langsmith.evaluation import EvaluationResult

from app.features.prospect_intelligence.public import PROSPECT_FILES
from evaluation.evaluators.file_contract import evaluate_file_contract
from tests.unit.evaluation.support import artifacts, outputs


def _metadata(result: EvaluationResult) -> dict[str, object]:
    return cast(
        "dict[str, object]",
        result.metadata,  # pyright: ignore[reportUnknownMemberType]
    )


def test_file_contract_checks_count_paths_json_and_schema() -> None:
    assert evaluate_file_contract(outputs(artifacts()), {}).score == 1.0
    malformed = artifacts()
    malformed[PROSPECT_FILES.lane_fit_json] = json.dumps({"method_version": "lane_fit_v1"})
    invalid = evaluate_file_contract(outputs(malformed), {})
    with_extra = artifacts()
    with_extra["/unexpected.txt"] = "extra"
    extra = evaluate_file_contract(outputs(with_extra), {})

    assert isinstance(invalid.score, (int, float)) and invalid.score < 1.0
    assert _metadata(invalid)["invalid_schema"] == [PROSPECT_FILES.lane_fit_json]
    assert _metadata(extra)["unexpected"] == ["/unexpected.txt"]
    missing_score = evaluate_file_contract({}, {}).score
    assert isinstance(missing_score, (int, float)) and missing_score < 1.0


def test_non_fit_file_contract_requires_exactly_the_non_review_artifacts() -> None:
    non_fit = artifacts(19)
    non_fit.pop(PROSPECT_FILES.outreach_draft)
    non_fit.pop(PROSPECT_FILES.review_findings)

    assert evaluate_file_contract(outputs(non_fit), {}).score == 1.0

    non_fit[PROSPECT_FILES.outreach_draft] = "unexpected outreach"
    unexpected = evaluate_file_contract(outputs(non_fit), {})
    assert isinstance(unexpected.score, (int, float)) and unexpected.score < 1.0
    assert _metadata(unexpected)["unexpected"] == [PROSPECT_FILES.outreach_draft]


def test_unavailable_source_with_no_evidence_is_a_valid_degraded_artifact() -> None:
    unavailable = artifacts()
    unavailable[PROSPECT_FILES.market_research] = json.dumps(
        {
            "sources": {},
            "coverage": [{"source": "FAF5 market data", "status": "unavailable"}],
            "evidence": [],
        }
    )

    assert evaluate_file_contract(outputs(unavailable), {}).score == 1.0
