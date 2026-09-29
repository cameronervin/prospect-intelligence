"""Checksummed FAF5.7.1 snapshot-backed market-data adapter."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from ...contracts.models import (
    Evidence,
    Provenance,
    SourceCoverage,
    SourceCoverageStatus,
    SourceMode,
)
from ...contracts.sources import MarketLane, SourceCallContext, SourceResult
from .snapshot import (
    FafSnapshotManifest,
    SnapshotRow,
    load_faf_snapshot_manifest,
    snapshot_rows,
    verify_faf_snapshot,
)

_ARTIFACT_PATH = (
    "app/features/prospect_intelligence/integrations/market_data/data/"
    "faf5_7_1_2023_truck_snapshot.csv"
)
_ESTIMATE_LABEL = "project-owned synthetic estimate"
_MIN_SHARE = Decimal("0.0025")
_MAX_SHARE = Decimal("0.0100")
_TONS_PER_LOAD = Decimal(20)
_WEEKS_PER_YEAR = Decimal(52)


@dataclass(frozen=True, slots=True)
class DerivedMarketLane:
    """FAF tonnage plus a deterministic fictional shipper-share estimate."""

    origin_zone: str
    destination_zone: str
    mode: str
    thousand_tons_2023: Decimal
    synthetic_shipper_share: Decimal
    estimated_loads_per_week: int
    estimate_label: str = _ESTIMATE_LABEL


def market_lane(row: SnapshotRow, share: Decimal) -> DerivedMarketLane:
    """Derive weekly loads from a reviewed fictional share of public regional tonnage."""

    if not share.is_finite() or not _MIN_SHARE <= share <= _MAX_SHARE:
        raise ValueError("synthetic shipper share must be between 0.25% and 1.0%")
    loads = (
        row.thousand_tons_2023 * Decimal(1000) * share / (_TONS_PER_LOAD * _WEEKS_PER_YEAR)
    ).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return DerivedMarketLane(
        origin_zone=row.origin_zone,
        destination_zone=row.destination_zone,
        mode="Truck",
        thousand_tons_2023=row.thousand_tons_2023,
        synthetic_shipper_share=share,
        estimated_loads_per_week=int(loads),
    )


class Faf5MarketDataSource:
    """Normalized market-data port backed by the committed FAF5.7.1 snapshot."""

    def __init__(self, *, synthetic_shipper_share: Decimal = Decimal("0.0050")) -> None:
        if (
            not synthetic_shipper_share.is_finite()
            or not _MIN_SHARE <= synthetic_shipper_share <= _MAX_SHARE
        ):
            raise ValueError("synthetic shipper share must be between 0.25% and 1.0%")
        self._share = synthetic_shipper_share

    def get_lane(
        self, context: SourceCallContext, origin_zone: str, destination_zone: str
    ) -> SourceResult[MarketLane]:
        cache_key = f"faf5:{self._share}:{origin_zone}:{destination_zone}"
        cached = context.cache.get(cache_key)
        if cached is not None:
            return cast(SourceResult[MarketLane], cached)
        row = next(
            (
                candidate
                for candidate in snapshot_rows()
                if candidate.origin_zone == origin_zone
                and candidate.destination_zone == destination_zone
            ),
            None,
        )
        if row is None:
            result = SourceResult[MarketLane](
                value=None,
                coverage=SourceCoverage(
                    source="FAF5.7.1 snapshot",
                    status=SourceCoverageStatus.UNAVAILABLE,
                    detail="lane is not present in the reviewed FAF snapshot",
                ),
                evidence=(),
            )
            context.cache.put(cache_key, result)
            return result
        derived = market_lane(row, self._share)
        manifest = load_faf_snapshot_manifest()
        retrieved_at = datetime.fromisoformat(manifest.retrieved_at).replace(tzinfo=UTC)
        result = SourceResult(
            value=MarketLane(
                origin_zone=derived.origin_zone,
                destination_zone=derived.destination_zone,
                mode=derived.mode,
                thousand_tons=derived.thousand_tons_2023,
                estimated_loads_per_week=derived.estimated_loads_per_week,
                estimate_label=derived.estimate_label,
            ),
            coverage=SourceCoverage(
                source="FAF5.7.1 snapshot", status=SourceCoverageStatus.COMPLETE
            ),
            evidence=(
                Evidence(
                    claim=(
                        "2023 regional truck-market tonnage used for a project-owned "
                        "synthetic estimate"
                    ),
                    provenance=Provenance(
                        source="BTS/FHWA FAF5.7.1",
                        mode=SourceMode.SNAPSHOT,
                        endpoint_or_artifact=_ARTIFACT_PATH,
                        retrieved_at=retrieved_at,
                        evidence_location=(
                            f"dms_orig={origin_zone},dms_dest={destination_zone},dms_mode=1"
                        ),
                        source_version="FAF5.7.1-2023-final",
                    ),
                ),
            ),
        )
        context.cache.put(cache_key, result)
        return result


__all__ = [
    "DerivedMarketLane",
    "Faf5MarketDataSource",
    "FafSnapshotManifest",
    "SnapshotRow",
    "load_faf_snapshot_manifest",
    "market_lane",
    "snapshot_rows",
    "verify_faf_snapshot",
]
