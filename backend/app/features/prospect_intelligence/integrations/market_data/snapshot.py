"""Loading and verification for the committed FAF5.7.1 snapshot."""

import csv
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import cast

_DATA_DIR = Path(__file__).parent / "data"
_MANIFEST_PATH = _DATA_DIR / "faf5_7_1_2023_truck_manifest.json"
_RELEASE = "FAF5.7.1"
_YEAR = 2023
_MODE_CODE = 1
_UNIT = "thousand short tons"
_SOURCE_URL = "https://faf.ornl.gov/faf5/data/download_files/FAF5.7.1_2018-2024.zip"
_DOI = "https://doi.org/10.21949/1529116"
_UPSTREAM_SHA256 = "803036bb693a81fdf3e2c4a6d561feb71b102470c1602e9b35e3094e79485b71"
_SOURCE_FILE = "FAF5.7.1_2018-2024.csv"
_EXTRACTION_FIELDS = ("dms_orig", "dms_dest", "dms_mode", "tons_2023")
_EXTRACTION_AGGREGATION = (
    "sum tons_2023 across commodity and trade rows by selected domestic origin/destination pair"
)


@dataclass(frozen=True, slots=True)
class FafSnapshotManifest:
    release: str
    year: int
    mode_code: int
    unit: str
    source_url: str
    doi: str
    retrieved_at: str
    upstream_sha256: str
    snapshot_path: str
    snapshot_sha256: str
    license_assumption: str
    source_file: str
    extraction_year: int
    extraction_mode_code: int
    extraction_fields: tuple[str, ...]
    extraction_aggregation: str
    origin_destination_pairs: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class SnapshotRow:
    origin_zone: str
    destination_zone: str
    thousand_tons_2023: Decimal


def _require_str(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise ValueError(f"FAF manifest field {key!r} must be a string")
    return value


def _require_int(raw: dict[str, object], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int):
        raise ValueError(f"FAF manifest field {key!r} must be an integer")
    return value


def load_faf_snapshot_manifest() -> FafSnapshotManifest:
    """Load the committed manifest and resolve its packaged artifact path."""

    parsed = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("FAF snapshot manifest must be an object")
    raw = cast(dict[str, object], parsed)
    extraction = raw.get("extraction")
    if not isinstance(extraction, dict):
        raise ValueError("FAF manifest extraction must be an object")
    extraction_raw = cast(dict[str, object], extraction)
    pairs_raw = extraction_raw.get("origin_destination_pairs")
    if not isinstance(pairs_raw, list):
        raise ValueError("FAF manifest origin-destination pairs must be a list")
    pairs: list[tuple[str, str]] = []
    for pair_value in cast(list[object], pairs_raw):
        if not isinstance(pair_value, list):
            raise ValueError("FAF manifest origin-destination pair is invalid")
        pair = cast(list[object], pair_value)
        if len(pair) != 2 or not all(isinstance(value, str) for value in pair):
            raise ValueError("FAF manifest origin-destination pair is invalid")
        pairs.append((cast(str, pair[0]), cast(str, pair[1])))
    fields_raw = extraction_raw.get("fields")
    if not isinstance(fields_raw, list):
        raise ValueError("FAF manifest extraction fields must be a list of strings")
    field_values = cast(list[object], fields_raw)
    if not all(isinstance(value, str) for value in field_values):
        raise ValueError("FAF manifest extraction fields must be a list of strings")
    snapshot = (_DATA_DIR / _require_str(raw, "snapshot_path")).resolve()
    if snapshot.parent != _DATA_DIR.resolve():
        raise ValueError("FAF snapshot path must remain inside the market-data package")
    return FafSnapshotManifest(
        release=_require_str(raw, "release"),
        year=_require_int(raw, "year"),
        mode_code=_require_int(raw, "mode_code"),
        unit=_require_str(raw, "unit"),
        source_url=_require_str(raw, "source_url"),
        doi=_require_str(raw, "doi"),
        retrieved_at=_require_str(raw, "retrieved_at"),
        upstream_sha256=_require_str(raw, "upstream_sha256"),
        snapshot_path=str(snapshot),
        snapshot_sha256=_require_str(raw, "snapshot_sha256"),
        license_assumption=_require_str(raw, "license_assumption"),
        source_file=_require_str(extraction_raw, "source_file"),
        extraction_year=_require_int(extraction_raw, "year"),
        extraction_mode_code=_require_int(extraction_raw, "mode_code"),
        extraction_fields=tuple(cast(str, value) for value in field_values),
        extraction_aggregation=_require_str(extraction_raw, "aggregation"),
        origin_destination_pairs=tuple(pairs),
    )


def verify_faf_snapshot() -> bool:
    """Verify checksum, release metadata, filters, row pairs, and finite tonnage."""

    manifest = load_faf_snapshot_manifest()
    if (
        manifest.release != _RELEASE
        or manifest.year != _YEAR
        or manifest.mode_code != _MODE_CODE
        or manifest.unit != _UNIT
        or manifest.source_url != _SOURCE_URL
        or manifest.doi != _DOI
        or manifest.upstream_sha256 != _UPSTREAM_SHA256
        or manifest.source_file != _SOURCE_FILE
        or manifest.extraction_year != _YEAR
        or manifest.extraction_mode_code != _MODE_CODE
        or manifest.extraction_fields != _EXTRACTION_FIELDS
        or manifest.extraction_aggregation != _EXTRACTION_AGGREGATION
    ):
        raise ValueError("FAF snapshot provenance does not match the reviewed extraction")
    snapshot = Path(manifest.snapshot_path)
    if hashlib.sha256(snapshot.read_bytes()).hexdigest() != manifest.snapshot_sha256:
        raise ValueError("FAF snapshot checksum does not match its manifest")
    with snapshot.open(encoding="utf-8", newline="") as handle:
        rows = tuple(csv.DictReader(handle))
    if not rows:
        raise ValueError("FAF snapshot must contain at least one row")
    if any(row.get("dms_mode") != str(manifest.mode_code) for row in rows):
        raise ValueError("FAF snapshot contains a non-truck mode")
    try:
        tonnages = tuple(Decimal(row["tons_2023_thousands"]) for row in rows)
        observed_pairs = tuple((row["dms_orig"], row["dms_dest"]) for row in rows)
    except (KeyError, ValueError) as error:
        raise ValueError("FAF snapshot has an invalid schema or tonnage") from error
    if any(not value.is_finite() or value < 0 for value in tonnages):
        raise ValueError("FAF snapshot contains invalid tonnage")
    if observed_pairs != manifest.origin_destination_pairs:
        raise ValueError("FAF snapshot rows do not match the reviewed extraction pairs")
    return True


def snapshot_rows() -> tuple[SnapshotRow, ...]:
    verify_faf_snapshot()
    manifest = load_faf_snapshot_manifest()
    with Path(manifest.snapshot_path).open(encoding="utf-8", newline="") as handle:
        rows = tuple(csv.DictReader(handle))
    return tuple(
        SnapshotRow(
            origin_zone=row["dms_orig"],
            destination_zone=row["dms_dest"],
            thousand_tons_2023=Decimal(row["tons_2023_thousands"]),
        )
        for row in rows
    )
