"""Authoritative lane_fit_v1 decision shared by the agent tool and the committed output."""

from app.features.prospect_intelligence.contracts.lane_analysis import LaneAnalysisArtifact
from app.features.prospect_intelligence.contracts.models import FitVerdict, SourceCoverageStatus
from app.features.prospect_intelligence.contracts.sources import (
    CarrierNetwork,
    FreightActivity,
    SourceResult,
)
from app.features.prospect_intelligence.domain.lane_fit import rank_lane_fits


def analyze_lanes(
    freight: SourceResult[FreightActivity],
    network: SourceResult[CarrierNetwork],
) -> LaneAnalysisArtifact:
    """Return needs_more_data unless both sources are complete and freight lanes exist."""

    if (
        freight.value is None
        or freight.coverage.status is not SourceCoverageStatus.COMPLETE
        or network.value is None
        or network.coverage.status is not SourceCoverageStatus.COMPLETE
        or not freight.value.lanes
    ):
        return LaneAnalysisArtifact.lane_fit_v1(FitVerdict.NEEDS_MORE_DATA, ())
    ranked = rank_lane_fits(freight.value.lanes, network.value.lanes)
    return LaneAnalysisArtifact.lane_fit_v1(FitVerdict.FIT if ranked else FitVerdict.NO_FIT, ranked)
