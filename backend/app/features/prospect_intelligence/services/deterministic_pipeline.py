"""Credential-free prospect worker used by tests and the local Docker demo."""

from uuid import UUID

from ..contracts.models import (
    AnalysisOutput,
    FitVerdict,
    OutreachDraft,
    ProspectBrief,
    RecommendedNextStep,
    RunStatus,
    ScoredLane,
    SourceCoverage,
    SourceCoverageStatus,
)
from ..contracts.sources import ProspectSources, RunSourceCache, SourceCallContext
from ..domain.lane_fit import rank_lane_fits
from .runs import ProspectRunService


class DeterministicProspectPipeline:
    """Execute the same business boundary as the live graph through source ports."""

    def __init__(self, service: ProspectRunService, sources: ProspectSources) -> None:
        self._service = service
        self._sources = sources

    def run(self, run_id: UUID, claim_token: UUID | None = None) -> None:
        current = self._service.get_run(run_id)
        if current.status not in {RunStatus.QUEUED, RunStatus.RUNNING}:
            return
        running = (
            self._service.start_run(run_id, claim_token=claim_token)
            if current.status is RunStatus.QUEUED
            else current
        )
        context = SourceCallContext(
            run_id=running.id,
            tenant_id=running.tenant_id,
            rep_id=running.rep_id,
            cache=RunSourceCache(running.id, running.tenant_id, running.rep_id),
        )
        freight = self._sources.freight.get_activity(context, running.account)
        network = self._sources.network.get_network(context)
        if (
            freight.value is None
            or freight.coverage.status is not SourceCoverageStatus.COMPLETE
            or network.value is None
            or network.coverage.status is not SourceCoverageStatus.COMPLETE
            or not freight.value.lanes
        ):
            self._submit_needs_more_data(
                run_id,
                (freight.coverage, network.coverage),
                claim_token,
            )
            return

        try:
            ranked = rank_lane_fits(freight.value.lanes, network.value.lanes)
        except (ArithmeticError, TypeError, ValueError):
            self._submit_needs_more_data(
                run_id,
                (freight.coverage, network.coverage),
                claim_token,
            )
            return

        has_direct_match = bool(ranked)
        verdict = FitVerdict.FIT if has_direct_match else FitVerdict.NO_FIT
        top_lane = ranked[0] if ranked else None
        outreach = (
            OutreachDraft(
                subject=(
                    f"{top_lane.origin} to {top_lane.destination} freight conversation"
                    if top_lane is not None
                    else "Freight conversation"
                ),
                body=(
                    f"Would you be open to comparing notes on your {top_lane.origin}-to-"
                    f"{top_lane.destination} freight needs?"
                    if top_lane is not None
                    else "Would you be open to comparing notes on your freight needs?"
                ),
            )
            if verdict is FitVerdict.FIT
            else None
        )
        self._service.submit_analysis(
            run_id,
            AnalysisOutput(
                verdict=verdict,
                brief=ProspectBrief(
                    markdown=(
                        "Direct lane evidence supports a carrier-sales conversation."
                        if has_direct_match
                        else "No direct lane overlap with usable capacity was found."
                    ),
                    summary=(
                        "Reviewed freight and carrier-network evidence shows a direct lane overlap "
                        "worth a sales conversation."
                        if has_direct_match
                        else "Reviewed freight and carrier-network evidence shows no direct lane "
                        "overlap with usable capacity."
                    ),
                    recommended_next_step=(
                        RecommendedNextStep.NEW_LANE_PITCH
                        if has_direct_match
                        else RecommendedNextStep.NOT_A_FIT
                    ),
                    recommendation=(
                        "Review the evidence-backed outreach before simulated send."
                        if has_direct_match
                        else "Do not prioritize outreach for this account."
                    ),
                    lanes=tuple(
                        ScoredLane(score=lane, evidence=freight.evidence + network.evidence)
                        for lane in ranked
                    ),
                ),
                outreach=outreach,
                source_coverage=(freight.coverage, network.coverage),
            ),
            claim_token=claim_token,
        )

    def _submit_needs_more_data(
        self,
        run_id: UUID,
        source_coverage: tuple[SourceCoverage, SourceCoverage],
        claim_token: UUID | None,
    ) -> None:
        self._service.submit_analysis(
            run_id,
            AnalysisOutput(
                verdict=FitVerdict.NEEDS_MORE_DATA,
                brief=ProspectBrief(
                    summary="The available source coverage does not support a lane recommendation.",
                    markdown="No usable lane-level freight and network evidence is available.",
                    recommended_next_step=RecommendedNextStep.NEEDS_MORE_DATA,
                    recommendation="Verify shipper lanes before outreach.",
                    lanes=(),
                ),
                outreach=None,
                source_coverage=source_coverage,
            ),
            claim_token=claim_token,
        )
