"""Serialize typed analysis output to and from PostgreSQL JSON values."""

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from ...contracts.models import (
    AnalysisOutput,
    Evidence,
    FitVerdict,
    OutreachDraft,
    ProspectBrief,
    Provenance,
    RecommendedNextStep,
    ScoredLane,
    SourceCoverage,
    SourceCoverageStatus,
    SourceMode,
)
from ...domain.models import LaneFitResult


def serialize_analysis_output(output: AnalysisOutput | None) -> dict[str, object] | None:
    if output is None:
        return None
    return {
        "verdict": output.verdict.value,
        "brief": {
            "summary": output.brief.summary,
            "markdown": output.brief.markdown,
            "recommended_next_step": output.brief.recommended_next_step.value,
            "recommendation": output.brief.recommendation,
            "lanes": [
                {
                    "score": _serialize_score(lane.score),
                    "evidence": [_serialize_evidence(item) for item in lane.evidence],
                }
                for lane in output.brief.lanes
            ],
        },
        "outreach": (
            {"subject": output.outreach.subject, "body": output.outreach.body}
            if output.outreach is not None
            else None
        ),
        "source_coverage": [
            {
                "source": coverage.source,
                "status": coverage.status.value,
                "detail": coverage.detail,
                "mode": coverage.mode.value if coverage.mode is not None else None,
            }
            for coverage in output.source_coverage
        ],
        "evidence": [_serialize_evidence(item) for item in output.evidence],
    }


def deserialize_analysis_output(raw: Mapping[str, Any] | None) -> AnalysisOutput | None:
    if raw is None:
        return None
    brief = cast("Mapping[str, Any]", raw["brief"])
    outreach = cast("Mapping[str, Any] | None", raw.get("outreach"))
    return AnalysisOutput(
        verdict=FitVerdict(raw["verdict"]),
        brief=ProspectBrief(
            summary=str(brief["summary"]),
            markdown=str(brief["markdown"]),
            recommended_next_step=RecommendedNextStep(brief["recommended_next_step"]),
            recommendation=str(brief["recommendation"]),
            lanes=tuple(
                ScoredLane(
                    score=_deserialize_score(cast("Mapping[str, Any]", lane["score"])),
                    evidence=tuple(
                        _deserialize_evidence(cast("Mapping[str, Any]", item))
                        for item in lane["evidence"]
                    ),
                )
                for lane in brief["lanes"]
            ),
        ),
        outreach=(
            OutreachDraft(subject=str(outreach["subject"]), body=str(outreach["body"]))
            if outreach is not None
            else None
        ),
        source_coverage=tuple(
            SourceCoverage(
                source=str(item["source"]),
                status=SourceCoverageStatus(item["status"]),
                detail=_optional_str(item.get("detail")),
                mode=_optional_source_mode(item.get("mode")),
            )
            for item in raw["source_coverage"]
        ),
        evidence=tuple(
            _deserialize_evidence(cast("Mapping[str, Any]", item))
            for item in cast("list[object]", raw.get("evidence", []))
        ),
    )


def _serialize_score(lane: LaneFitResult) -> dict[str, object]:
    return {
        "origin": lane.origin,
        "destination": lane.destination,
        "shipper_loads_per_week": lane.shipper_loads_per_week,
        "matched_loads_per_week": lane.matched_loads_per_week,
        "backhaul_fill": str(lane.backhaul_fill),
        "density": str(lane.density),
        "equipment_match": str(lane.equipment_match),
        "fit_score": str(lane.fit_score),
        "modeled_annual_revenue": str(lane.modeled_annual_revenue),
        "deadhead_miles_avoided": lane.deadhead_miles_avoided,
        "method_version": lane.method_version,
    }


def _deserialize_score(raw: Mapping[str, Any]) -> LaneFitResult:
    return LaneFitResult(
        origin=str(raw["origin"]),
        destination=str(raw["destination"]),
        shipper_loads_per_week=int(raw["shipper_loads_per_week"]),
        matched_loads_per_week=int(raw["matched_loads_per_week"]),
        backhaul_fill=Decimal(str(raw["backhaul_fill"])),
        density=Decimal(str(raw["density"])),
        equipment_match=Decimal(str(raw["equipment_match"])),
        fit_score=Decimal(str(raw["fit_score"])),
        modeled_annual_revenue=Decimal(str(raw["modeled_annual_revenue"])),
        deadhead_miles_avoided=int(raw["deadhead_miles_avoided"]),
        method_version=str(raw["method_version"]),
    )


def _serialize_evidence(evidence: Evidence) -> dict[str, object]:
    return {
        "claim": evidence.claim,
        "provenance": {
            "source": evidence.provenance.source,
            "mode": evidence.provenance.mode.value,
            "endpoint_or_artifact": evidence.provenance.endpoint_or_artifact,
            "retrieved_at": evidence.provenance.retrieved_at.isoformat(),
            "evidence_location": evidence.provenance.evidence_location,
            "source_version": evidence.provenance.source_version,
        },
    }


def _deserialize_evidence(raw: Mapping[str, Any]) -> Evidence:
    provenance = cast("Mapping[str, Any]", raw["provenance"])
    return Evidence(
        claim=str(raw["claim"]),
        provenance=Provenance(
            source=str(provenance["source"]),
            mode=SourceMode(provenance["mode"]),
            endpoint_or_artifact=str(provenance["endpoint_or_artifact"]),
            retrieved_at=datetime.fromisoformat(str(provenance["retrieved_at"])),
            evidence_location=str(provenance["evidence_location"]),
            source_version=str(provenance["source_version"]),
        ),
    )


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_source_mode(value: object) -> SourceMode | None:
    return SourceMode(str(value)) if value is not None else None
