"""FAF5 snapshot market-data adapter behavior."""

import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from app.features.prospect_intelligence.contracts import (
    MarketDataSource,
    RunSourceCache,
    SourceCallContext,
    SourceCoverageStatus,
    SourceMode,
)
from app.features.prospect_intelligence.integrations.market_data import faf5 as faf_module
from app.features.prospect_intelligence.integrations.market_data import snapshot as snapshot_module
from app.features.prospect_intelligence.integrations.market_data.faf5 import (
    Faf5MarketDataSource,
    load_faf_snapshot_manifest,
    market_lane,
    snapshot_rows,
    verify_faf_snapshot,
)


def _context(run_id: int = 1) -> SourceCallContext:
    parsed = UUID(f"00000000-0000-0000-0000-{run_id:012d}")
    return SourceCallContext(
        run_id=parsed,
        tenant_id="tenant-a",
        rep_id="rep-a",
        cache=RunSourceCache(run_id=parsed, tenant_id="tenant-a", rep_id="rep-a"),
    )


def test_faf_market_source_conforms_and_returns_normalized_lane_with_exact_evidence() -> None:
    source = Faf5MarketDataSource(synthetic_shipper_share=Decimal("0.0050"))

    assert isinstance(source, MarketDataSource)

    result = source.get_lane(_context(), "041", "061")

    assert result.coverage.status is SourceCoverageStatus.COMPLETE
    assert result.value is not None
    assert result.value.origin_zone == "041"
    assert result.value.destination_zone == "061"
    assert result.value.mode == "Truck"
    assert result.value.thousand_tons == Decimal("3221.013040")
    assert result.value.estimated_loads_per_week == 15
    assert result.value.estimate_label == "project-owned synthetic estimate"
    assert math.isfinite(float(result.value.thousand_tons))
    assert result.evidence[0].provenance.mode is SourceMode.SNAPSHOT
    assert result.evidence[0].provenance.endpoint_or_artifact == (
        "app/features/prospect_intelligence/integrations/market_data/data/"
        "faf5_7_1_2023_truck_snapshot.csv"
    )
    assert result.evidence[0].provenance.evidence_location == (
        "dms_orig=041,dms_dest=061,dms_mode=1"
    )


def test_faf_market_source_returns_terminal_unavailable_and_caches_per_run() -> None:
    source = Faf5MarketDataSource()
    context = _context()

    first_complete = source.get_lane(context, "041", "061")
    second_complete = source.get_lane(context, "041", "061")
    first_missing = source.get_lane(context, "000", "999")
    second_missing = source.get_lane(context, "000", "999")

    assert second_complete is first_complete
    assert first_missing.value is None
    assert first_missing.coverage.status is SourceCoverageStatus.UNAVAILABLE
    assert first_missing.coverage.detail == "lane is not present in the reviewed FAF snapshot"
    assert first_missing.evidence == ()
    assert second_missing is first_missing
    assert source.get_lane(_context(2), "041", "061") is not first_complete


def test_faf_snapshot_manifest_and_artifact_are_verified_at_the_new_package_path() -> None:
    manifest = load_faf_snapshot_manifest()
    snapshot = Path(manifest.snapshot_path)

    assert snapshot.parent == Path(faf_module.__file__).parent / "data"
    assert snapshot.is_file()
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == manifest.snapshot_sha256
    assert manifest.release == "FAF5.7.1"
    assert manifest.origin_destination_pairs[0] == ("041", "061")
    assert verify_faf_snapshot() is True


def test_all_reviewed_rows_produce_finite_nonnegative_boundary_estimates() -> None:
    for row in snapshot_rows():
        assert row.thousand_tons_2023.is_finite()
        for share in (Decimal("0.0025"), Decimal("0.0100")):
            lane = market_lane(row, share)
            assert lane.thousand_tons_2023.is_finite()
            assert lane.estimated_loads_per_week >= 0
            assert lane.estimate_label == "project-owned synthetic estimate"


def test_faf_snapshot_rejects_tampered_manifest_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = cast(
        dict[str, object],
        json.loads(snapshot_module._MANIFEST_PATH.read_text(encoding="utf-8")),  # pyright: ignore[reportPrivateUsage]
    )
    raw["release"] = "FAF5.7.0"
    manifest_path = tmp_path / "tampered-manifest.json"
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(snapshot_module, "_MANIFEST_PATH", manifest_path)

    with pytest.raises(ValueError, match="reviewed extraction"):
        verify_faf_snapshot()


@pytest.mark.parametrize("share", (Decimal("0.0024"), Decimal("0.0101")))
def test_faf_market_source_rejects_shares_outside_reviewed_range(share: Decimal) -> None:
    with pytest.raises(ValueError, match=r"between 0\.25% and 1\.0%"):
        Faf5MarketDataSource(synthetic_shipper_share=share)
