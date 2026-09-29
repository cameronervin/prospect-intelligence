"""Final shared-contract invariants for prospect intelligence."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.features.prospect_intelligence.contracts.filesystem import PROSPECT_FILES
from app.features.prospect_intelligence.contracts.models import (
    AnalysisOutput,
    Evidence,
    FitVerdict,
    OutreachDraft,
    ProspectBrief,
    Provenance,
    RecommendedNextStep,
    RunError,
    RunStatus,
    ScoredLane,
    SourceCoverage,
    SourceCoverageStatus,
    SourceMode,
)
from app.features.prospect_intelligence.domain.models import LaneFitResult
from app.features.prospect_intelligence.repositories.postgres.analysis_codec import (
    deserialize_analysis_output,
    serialize_analysis_output,
)
from app.features.prospect_intelligence.repositories.postgres.run_codec import (
    deserialize_outreach,
    deserialize_run_error,
    serialize_outreach,
    serialize_run_error,
)


def test_analysis_output_uses_distinct_typed_business_contracts() -> None:
    assert tuple(status.value for status in RunStatus) == (
        "queued",
        "running",
        "awaiting_review",
        "completed",
        "rejected",
        "failed",
    )
    assert FitVerdict.NEEDS_MORE_DATA.value not in {status.value for status in RunStatus}
    provenance = Provenance(
        source="GenLogs fixture",
        mode=SourceMode.FIXTURE,
        endpoint_or_artifact="fixtures/genlogs/acme-foods.json",
        retrieved_at=datetime(2026, 9, 29, 12, tzinfo=UTC),
        evidence_location="$.lanes[0].weekly_loads",
        source_version="synthetic-v1",
    )
    scored_lane = ScoredLane(
        score=LaneFitResult(
            origin="ATL",
            destination="DAL",
            shipper_loads_per_week=12,
            matched_loads_per_week=8,
            backhaul_fill=Decimal("1"),
            density=Decimal("0.6"),
            equipment_match=Decimal("0.9"),
            fit_score=Decimal("0.86"),
            modeled_annual_revenue=Decimal("624000"),
            deadhead_miles_avoided=332_800,
        ),
        evidence=(Evidence(claim="12 observed loads per week", provenance=provenance),),
    )

    output = AnalysisOutput(
        verdict=FitVerdict.FIT,
        brief=ProspectBrief(
            summary="Direct lane overlap.",
            markdown="# Supported brief",
            recommended_next_step=RecommendedNextStep.NEW_LANE_PITCH,
            recommendation="Pitch the supported lane.",
            lanes=(scored_lane,),
        ),
        outreach=OutreachDraft(subject="Capacity", body="Could we compare lanes?"),
        source_coverage=(
            SourceCoverage(
                source="GenLogs",
                status=SourceCoverageStatus.DEGRADED,
                detail="Fixture mode",
            ),
        ),
    )

    assert output.verdict is FitVerdict.FIT
    assert output.brief.recommended_next_step is RecommendedNextStep.NEW_LANE_PITCH
    assert output.brief.lanes[0].evidence[0].provenance == provenance
    assert deserialize_analysis_output(serialize_analysis_output(output)) == output
    assert deserialize_outreach(serialize_outreach(output.outreach)) == output.outreach
    run_error = RunError(code="source_unavailable", message="Source unavailable", retryable=True)
    assert deserialize_run_error(serialize_run_error(run_error)) == run_error


def test_filesystem_contract_is_canonical_and_rejects_unsafe_memory_scopes() -> None:
    assert PROSPECT_FILES.required_artifacts() == tuple(
        entry.path for entry in PROSPECT_FILES.manifest_entries()
    )
    assert "/research/freight_intel/lanes.json" in PROSPECT_FILES.required_artifacts()
    assert "/research/company/company.json" in PROSPECT_FILES.required_artifacts()
    assert "/research/market/volumes.json" in PROSPECT_FILES.required_artifacts()
    assert PROSPECT_FILES.rep_memory("tenant-demo", "rep-demo") == (
        "/memories/tenant-demo/rep-demo/preferences.md"
    )

    with pytest.raises(ValueError, match="scope identifier"):
        PROSPECT_FILES.rep_memory("../tenant", "rep-demo")
