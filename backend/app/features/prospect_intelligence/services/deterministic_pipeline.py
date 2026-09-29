"""Credential-free prospect worker used by tests and the local Docker demo."""

from typing import Protocol
from uuid import UUID

from ..contracts.models import AnalysisOutput, Evidence, FitVerdict, SourceCoverage
from ..domain.lane_fit import score_lane
from ..domain.models import NetworkLane, ShipperLane
from .runs import ProspectRunService


class ProspectSourceData(Protocol):
    @property
    def account_id(self) -> str: ...

    @property
    def shipper_lanes(self) -> tuple[ShipperLane, ...]: ...

    @property
    def network_lanes(self) -> tuple[NetworkLane, ...]: ...

    @property
    def evidence(self) -> tuple[Evidence, ...]: ...


class DeterministicProspectPipeline:
    """Execute the same business boundary as the live graph using reviewed fixtures."""

    def __init__(
        self,
        service: ProspectRunService,
        sources: tuple[ProspectSourceData, ...],
    ) -> None:
        self._service = service
        self._sources = sources

    def run(self, run_id: UUID) -> None:
        running = self._service.start_run(run_id)
        source = next(
            (item for item in self._sources if item.account_id == running.account.id),
            None,
        )
        if source is None:
            self._service.submit_analysis(
                run_id,
                AnalysisOutput(
                    verdict=FitVerdict.NEEDS_MORE_DATA,
                    brief_markdown="No lane-level freight evidence is available for this account.",
                    brief_summary=(
                        "The account is known, but the available fixtures do not support a "
                        "lane recommendation."
                    ),
                    recommended_next_step="Verify shipper lanes before outreach.",
                    outreach_draft=None,
                    scored_lanes=(),
                    source_coverage=(
                        SourceCoverage(
                            source="Freight intelligence",
                            status="unavailable",
                            detail="No reviewed fixture or live result was available.",
                        ),
                    ),
                ),
            )
            return

        scored = tuple(
            score_lane(
                shipper,
                next(
                    (
                        lane
                        for lane in source.network_lanes
                        if (lane.origin, lane.destination) == (shipper.origin, shipper.destination)
                    ),
                    None,
                ),
            )
            for shipper in source.shipper_lanes
        )
        ranked = tuple(sorted(scored, key=lambda lane: lane.fit_score, reverse=True)[:3])
        has_direct_match = any(lane.matched_loads_per_week > 0 for lane in ranked)
        verdict = FitVerdict.FIT if has_direct_match else FitVerdict.NO_FIT
        outreach = (
            "Would you be open to comparing notes on your Atlanta-to-Dallas freight needs? "
            "Our network may be able to support that lane."
            if verdict is FitVerdict.FIT
            else None
        )
        self._service.submit_analysis(
            run_id,
            AnalysisOutput(
                verdict=verdict,
                brief_markdown="Direct lane evidence supports a carrier-sales conversation.",
                brief_summary=(
                    "Reviewed freight and carrier-network fixtures show a direct lane overlap "
                    "worth a sales conversation."
                ),
                recommended_next_step=(
                    "Review the evidence-backed outreach before simulated send."
                    if has_direct_match
                    else "Do not prioritize outreach for this account."
                ),
                outreach_subject="Atlanta to Dallas capacity conversation",
                outreach_draft=outreach,
                scored_lanes=ranked,
                source_coverage=(
                    SourceCoverage(
                        source="GenLogs",
                        status="degraded",
                        detail="Deterministic synthetic fixture; no live credential was used.",
                    ),
                    SourceCoverage(
                        source="Carrier network",
                        status="complete",
                        detail="Tenant-scoped synthetic network fixture.",
                    ),
                ),
                lane_evidence=tuple((source.evidence) for _lane in ranked),
            ),
        )
