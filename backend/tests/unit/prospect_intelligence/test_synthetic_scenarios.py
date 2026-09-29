"""Shared deterministic synthetic source and FAF snapshot contracts."""

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from app.features.prospect_intelligence.integrations.market_data import snapshot as snapshot_module
from app.features.prospect_intelligence.public import (
    SYNTHETIC_DATASET_SEED,
    SYNTHETIC_DATASET_VERSION,
    canonical_scenarios_bytes,
    generate_synthetic_scenarios,
    load_faf_snapshot_manifest,
    verify_faf_snapshot,
)


def test_shared_generator_builds_seeded_offline_and_traffic_pools() -> None:
    first = generate_synthetic_scenarios(seed=SYNTHETIC_DATASET_SEED)
    second = generate_synthetic_scenarios(seed=SYNTHETIC_DATASET_SEED)

    assert first == second
    assert SYNTHETIC_DATASET_VERSION == "freight-prospect-v1"
    assert len(first) == 32
    assert sum(item.split == "core" for item in first) == 16
    assert sum(item.split == "edge" for item in first) == 8
    assert sum(item.split == "traffic" for item in first) == 8
    assert len({item.account.account_id for item in first}) == len(first)

    offline_ids = {item.account.account_id for item in first if item.split != "traffic"}
    traffic_ids = {item.account.account_id for item in first if item.split == "traffic"}
    assert offline_ids.isdisjoint(traffic_ids)


def test_canonical_scenario_bytes_are_repeatable() -> None:
    first = canonical_scenarios_bytes()
    second = canonical_scenarios_bytes()

    assert first == second
    assert first.endswith(b"\n")
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()


def test_faf_snapshot_manifest_and_derived_estimates_are_verified() -> None:
    manifest = load_faf_snapshot_manifest()
    snapshot_path = Path(manifest.snapshot_path)

    assert manifest.release == "FAF5.7.1"
    assert manifest.year == 2023
    assert manifest.mode_code == 1
    assert manifest.doi == "https://doi.org/10.21949/1529116"
    assert manifest.source_url.startswith("https://faf.ornl.gov/")
    assert manifest.retrieved_at == "2026-09-29"
    assert manifest.upstream_sha256
    assert manifest.source_file == "FAF5.7.1_2018-2024.csv"
    assert manifest.extraction_year == 2023
    assert manifest.extraction_mode_code == 1
    assert manifest.extraction_fields == (
        "dms_orig",
        "dms_dest",
        "dms_mode",
        "tons_2023",
    )
    assert manifest.extraction_aggregation.startswith("sum tons_2023")
    assert manifest.origin_destination_pairs == (
        ("041", "061"),
        ("061", "041"),
        ("081", "531"),
        ("131", "484"),
        ("171", "471"),
        ("471", "171"),
        ("484", "131"),
        ("531", "081"),
    )
    assert snapshot_path.is_file()
    assert hashlib.sha256(snapshot_path.read_bytes()).hexdigest() == manifest.snapshot_sha256
    assert verify_faf_snapshot() is True


@pytest.mark.parametrize(
    ("field", "tampered"),
    (
        ("year", 2022),
        ("mode_code", 2),
        ("fields", ["dms_orig", "tons_2022"]),
        ("aggregation", "take the first matching row"),
    ),
)
def test_faf_snapshot_rejects_tampered_extraction_provenance(
    field: str,
    tampered: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = cast(
        dict[str, object],
        json.loads(
            snapshot_module._MANIFEST_PATH.read_text(  # pyright: ignore[reportPrivateUsage]
                encoding="utf-8"
            )
        ),
    )
    extraction = cast(dict[str, object], raw["extraction"])
    extraction[field] = tampered
    manifest_path = tmp_path / "tampered-manifest.json"
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(snapshot_module, "_MANIFEST_PATH", manifest_path)

    with pytest.raises(ValueError, match="reviewed extraction"):
        verify_faf_snapshot()


def test_offline_citations_resolve_to_exact_committed_evidence() -> None:
    backend_root = Path(__file__).parents[3]

    for scenario in generate_synthetic_scenarios():
        for evidence in scenario.citations:
            location = evidence.provenance.evidence_location
            if evidence.provenance.source == "BTS/FHWA FAF5.7.1":
                assert (backend_root / evidence.provenance.endpoint_or_artifact).is_file()
                market = scenario.market_lanes[0]
                assert f"dms_orig={market.origin_zone}" in location
                assert f"dms_dest={market.destination_zone}" in location
                assert "dms_mode=1" in location
            elif scenario.split != "traffic":
                assert (backend_root / evidence.provenance.endpoint_or_artifact).is_file()
                assert scenario.scenario_id in location

    missing_coverage = next(
        scenario for scenario in generate_synthetic_scenarios() if scenario.scenario_id == "edge_01"
    )
    genlogs = next(
        evidence
        for evidence in missing_coverage.citations
        if evidence.provenance.source == "GenLogs fixture"
    )
    assert "unavailable" in genlogs.claim
