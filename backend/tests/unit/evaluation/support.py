"""Shared deterministic fixtures for evaluator unit tests."""

import json
from collections.abc import Mapping
from dataclasses import asdict

from app.features.prospect_intelligence.public import PROSPECT_FILES
from evaluation.contracts.observations import (
    file_contract_observation,
    numeric_evidence_observation,
)
from evaluation.datasets import generate_dataset


def source_artifact(**values: object) -> str:
    return json.dumps(
        {
            **values,
            "coverage": {"source": "synthetic", "status": "complete"},
            "evidence": [
                {
                    "claim": "synthetic evidence",
                    "provenance": {
                        "source": "synthetic",
                        "mode": "fixture",
                        "endpoint_or_artifact": "fixture://synthetic",
                        "retrieved_at": "2026-09-29T00:00:00+00:00",
                        "evidence_location": "record:1",
                        "source_version": "v1",
                    },
                }
            ],
        }
    )


def lane_artifact(example_index: int = 0) -> str:
    example = generate_dataset()[example_index]
    decimal_fields = {
        "backhaul_fill",
        "density",
        "equipment_match",
        "fit_score",
        "modeled_annual_revenue",
    }
    return json.dumps(
        {
            "method_version": "lane_fit_v1",
            "verdict": example.expected_verdict.value,
            "top_lanes": [
                {
                    key: str(value) if key in decimal_fields else value
                    for key, value in asdict(lane).items()
                }
                for lane in example.expected_lane_scores
            ],
        }
    )


def artifacts(example_index: int = 0) -> dict[str, str]:
    return {
        PROSPECT_FILES.task_brief: "Research the synthetic prospect.",
        PROSPECT_FILES.index: "# Prospect artifact manifest\n",
        PROSPECT_FILES.account_context: source_artifact(account="Synthetic"),
        PROSPECT_FILES.network_context: source_artifact(lanes=[]),
        PROSPECT_FILES.company_research: source_artifact(signals=[]),
        PROSPECT_FILES.freight_research: source_artifact(rate=1250, share=0.25),
        PROSPECT_FILES.market_research: source_artifact(year=2023),
        PROSPECT_FILES.lane_fit_json: lane_artifact(example_index),
        PROSPECT_FILES.lane_fit_markdown: "# Lane fit\n",
        PROSPECT_FILES.sales_brief: "A supported rate is $1,250 and the share is 25%.",
        PROSPECT_FILES.outreach_draft: "Subject: Freight fit\n\nA supported rate is $1,250.",
        PROSPECT_FILES.review_findings: json.dumps(
            {"round": 1, "verdict": "pass", "findings": [], "resolved_prior": []}
        ),
    }


def outputs(all_artifacts: Mapping[str, str]) -> dict[str, object]:
    model_paths = (
        PROSPECT_FILES.lane_fit_json,
        PROSPECT_FILES.lane_fit_markdown,
        PROSPECT_FILES.sales_brief,
        PROSPECT_FILES.outreach_draft,
    )
    return {
        "artifacts": {path: all_artifacts[path] for path in model_paths if path in all_artifacts},
        "artifact_observations": {
            "file_contract": file_contract_observation(all_artifacts),
            "numeric_evidence": numeric_evidence_observation(all_artifacts),
        },
        "tool_calls": ["task", "write_file", "send_outreach"],
    }
