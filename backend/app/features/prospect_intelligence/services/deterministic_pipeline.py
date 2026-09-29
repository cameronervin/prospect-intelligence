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
    SourceCoverageStatus,
)
from ..contracts.sources import ProspectSources, RunSourceCache, SourceCallContext
from ..domain.lane_fit import score_lane
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
            self._service.submit_analysis(
                run_id,
                AnalysisOutput(
                    verdict=FitVerdict.NEEDS_MORE_DATA,
                    brief=ProspectBrief(
                        summary=(
                            "The available source coverage does not support a lane recommendation."
                        ),
                        markdown="No usable lane-level freight and network evidence is available.",
                        recommended_next_step=RecommendedNextStep.NEEDS_MORE_DATA,
                        recommendation="Verify shipper lanes before outreach.",
                        lanes=(),
                    ),
                    outreach=None,
                    source_coverage=(freight.coverage, network.coverage),
                ),
                claim_token=claim_token,
            )
            return

        scored = tuple(
            score_lane(
                shipper,
                next(
                    (
                        lane
                        for lane in network.value.lanes
                        if (lane.origin, lane.destination) == (shipper.origin, shipper.destination)
                    ),
                    None,
                ),
            )
            for shipper in freight.value.lanes
        )
        ranked = tuple(sorted(scored, key=lambda lane: lane.fit_score, reverse=True)[:3])
        has_direct_match = any(lane.matched_loads_per_week > 0 for lane in ranked)
        verdict = FitVerdict.FIT if has_direct_match else FitVerdict.NO_FIT
        top_lane = ranked[0] if ranked else None
        outreach = (
            OutreachDraft(
                subject=(
                    f"{top_lane.origin} to {top_lane.destination} capacity conversation"
                    if top_lane is not None
                    else "Capacity conversation"
                ),
                body=(
                    f"Would you be open to comparing notes on your {top_lane.origin}-to-"
                    f"{top_lane.destination} freight needs? Our network may be able to support "
                    "that lane."
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
                    markdown="Direct lane evidence supports a carrier-sales conversation.",
                    summary=(
                        "Reviewed freight and carrier-network evidence shows a direct lane overlap "
                        "worth a sales conversation."
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
