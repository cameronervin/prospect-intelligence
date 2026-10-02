"""Projection of normalized source artifacts into persisted product evidence."""

import json
from datetime import UTC, datetime

import pytest

from app.features.prospect_intelligence.contracts.citations import evidence_citation_id
from app.features.prospect_intelligence.contracts.models import (
    SourceCoverage,
    SourceCoverageStatus,
)
from app.features.prospect_intelligence.contracts.progress import (
    RunStep,
    RunStepStatus,
    StepActivity,
    StepActivityOutcome,
)
from app.features.prospect_intelligence.services.agent_output import (
    project_source_artifacts,
    validate_progress_coverage,
)


def _evidence(
    source: str,
    location: str,
    *,
    claim: str | None = None,
) -> dict[str, object]:
    provenance = {
        "source": source,
        "mode": "fixture",
        "endpoint_or_artifact": f"fixture://{source}",
        "retrieved_at": "2026-09-29T00:00:00+00:00",
        "evidence_location": location,
        "source_version": "v1",
    }
    return {
        "claim": claim or f"Supported {source} claim",
        "citation_id": evidence_citation_id(provenance),
        "provenance": provenance,
    }


def _file(payload: object) -> dict[str, str]:
    return {"content": json.dumps(payload), "encoding": "utf-8"}


def test_projection_keeps_all_sources_and_aggregates_repeated_market_calls() -> None:
    files = {
        "/context/account.json": _file(
            {
                "value": {"name": "Acme Foods"},
                "coverage": {
                    "source": "CRM fixture",
                    "status": "complete",
                    "mode": "fixture",
                },
                "evidence": [_evidence("CRM fixture", "account")],
            }
        ),
        "/context/our_network.json": _file(
            {
                "value": {"lanes": []},
                "coverage": {
                    "source": "Carrier network fixture",
                    "status": "complete",
                    "mode": "fixture",
                },
                "evidence": [_evidence("Carrier network fixture", "network")],
            }
        ),
        "/research/freight_intel/lanes.json": _file(
            {
                "value": {"lanes": []},
                "coverage": {
                    "source": "GenLogs fixture",
                    "status": "complete",
                    "mode": "fixture",
                },
                "evidence": [_evidence("GenLogs fixture", "freight")],
            }
        ),
        "/research/company/company.json": _file(
            {
                "sources": {"search_sec": [], "search_tavily": []},
                "coverage": [
                    {"source": "SEC EDGAR", "status": "unavailable", "mode": "live"},
                    {"source": "Tavily Search", "status": "degraded", "mode": "live"},
                    {
                        "source": "FMCSA QCMobile",
                        "status": "unavailable",
                        "mode": "live",
                    },
                ],
                "evidence": [_evidence("Tavily Search", "web")],
            }
        ),
        "/research/market/volumes.json": _file(
            {
                "sources": {"ATL->DAL": {}, "DAL->ATL": None},
                "coverage": [
                    {
                        "source": "BTS/FHWA FAF5.7.1",
                        "status": "complete",
                        "mode": "snapshot",
                    },
                    {
                        "source": "BTS/FHWA FAF5.7.1",
                        "status": "unavailable",
                        "mode": "snapshot",
                        "detail": "lane unavailable",
                    },
                ],
                "evidence": [_evidence("BTS/FHWA FAF5.7.1", "lane:ATL-DAL")],
            }
        ),
    }

    projection = project_source_artifacts(files)

    assert [item.source for item in projection.coverage] == [
        "CRM fixture",
        "Carrier network fixture",
        "GenLogs fixture",
        "SEC EDGAR",
        "Tavily Search",
        "FMCSA QCMobile",
        "BTS/FHWA FAF5.7.1",
    ]
    assert projection.coverage[-1].status is SourceCoverageStatus.DEGRADED
    assert projection.coverage[-1].detail == "lane unavailable"
    assert len(projection.evidence) == 5


def test_projection_rejects_a_mismatched_tool_citation() -> None:
    item = _evidence("CRM account record", "account")
    item["citation_id"] = "ev_000000000000000000000000"
    files = {
        "/context/account.json": _file(
            {
                "value": {"name": "Acme Foods"},
                "coverage": {"source": "CRM account record", "status": "complete"},
                "evidence": [item],
            }
        )
    }

    with pytest.raises(ValueError, match="citation id"):
        project_source_artifacts(files)


def test_projection_rejects_missing_tool_citation_id() -> None:
    item = _evidence("CRM account record", "account")
    del item["citation_id"]
    files = {
        "/context/account.json": _file(
            {
                "value": {"name": "Acme Foods"},
                "coverage": {"source": "CRM account record", "status": "complete"},
                "evidence": [item],
            }
        )
    }

    with pytest.raises(ValueError, match="citation id"):
        project_source_artifacts(files)


def test_projection_deduplicates_exact_citation_claims() -> None:
    item = _evidence("CRM fixture", "account")
    files = {
        "/context/account.json": _file(
            {
                "value": {"name": "Acme Foods"},
                "coverage": {"source": "CRM fixture", "status": "complete"},
                "evidence": [item, dict(item)],
            }
        )
    }

    projection = project_source_artifacts(files)

    assert projection.evidence == (projection.evidence[0],)


def test_projection_rejects_nonidentical_whitespace_in_duplicate_claims() -> None:
    first = _evidence("CRM fixture", "account", claim="Acme is a food distributor.")
    equivalent = dict(first)
    equivalent["claim"] = "Acme  is a food\n distributor."
    files = {
        "/context/account.json": _file(
            {
                "value": {"name": "Acme Foods"},
                "coverage": {"source": "CRM fixture", "status": "complete"},
                "evidence": [first, equivalent],
            }
        )
    }

    with pytest.raises(ValueError, match="conflicting claims"):
        project_source_artifacts(files)


def test_projection_rejects_conflicting_claims_for_one_citation_id() -> None:
    first = _evidence("CRM fixture", "account", claim="Acme is a food distributor.")
    conflicting = dict(first)
    conflicting["claim"] = "Acme is a retail account."
    files = {
        "/context/account.json": _file(
            {
                "value": {"name": "Acme Foods"},
                "coverage": {"source": "CRM fixture", "status": "complete"},
                "evidence": [first, conflicting],
            }
        )
    }

    with pytest.raises(ValueError, match="conflicting claims"):
        project_source_artifacts(files)


def test_successful_progress_source_requires_final_coverage() -> None:
    steps = (
        RunStep(
            key="external-research",
            label="External research",
            status=RunStepStatus.COMPLETE,
            activity=(
                StepActivity(
                    at=datetime(2026, 9, 29, tzinfo=UTC),
                    source="FMCSA carrier registry",
                    outcome=StepActivityOutcome.OK,
                ),
            ),
        ),
    )

    with pytest.raises(ValueError, match="FMCSA"):
        validate_progress_coverage(
            steps,
            (SourceCoverage("SEC EDGAR", SourceCoverageStatus.COMPLETE),),
        )

    validate_progress_coverage(
        steps,
        (SourceCoverage("FMCSA QCMobile", SourceCoverageStatus.UNAVAILABLE),),
    )


def test_progress_coverage_rejects_spoofed_source_labels() -> None:
    steps = (
        RunStep(
            key="external-research",
            label="External research",
            status=RunStepStatus.COMPLETE,
            activity=(
                StepActivity(
                    at=datetime(2026, 9, 29, tzinfo=UTC),
                    source="FAF5 market volume",
                    outcome=StepActivityOutcome.OK,
                ),
            ),
        ),
    )

    with pytest.raises(ValueError, match="unknown source"):
        validate_progress_coverage(
            steps,
            (SourceCoverage("spoofed FAF result", SourceCoverageStatus.COMPLETE),),
        )


def test_progress_coverage_rejects_spoofed_activity_labels() -> None:
    steps = (
        RunStep(
            key="external-research",
            label="External research",
            status=RunStepStatus.COMPLETE,
            activity=(
                StepActivity(
                    at=datetime(2026, 9, 29, tzinfo=UTC),
                    source="FAF5 market volume from another provider",
                    outcome=StepActivityOutcome.OK,
                ),
            ),
        ),
    )

    with pytest.raises(ValueError, match="unknown progress source"):
        validate_progress_coverage(
            steps,
            (SourceCoverage("BTS/FHWA FAF5.7.1", SourceCoverageStatus.COMPLETE),),
        )
