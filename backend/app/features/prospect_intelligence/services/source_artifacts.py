"""Parse and aggregate normalized source artifacts."""

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast

from ..contracts.citations import evidence_citation_id
from ..contracts.models import (
    Evidence,
    Provenance,
    SourceCoverage,
    SourceCoverageStatus,
    SourceMode,
)


def parse_source_artifact(
    content: str,
    path: str,
) -> tuple[tuple[SourceCoverage, ...], tuple[tuple[str, Evidence], ...]]:
    payload = _json_object(content, path)
    return _parse_coverage(payload, path), _parse_evidence(payload, path)


def aggregate_coverage(values: Sequence[SourceCoverage]) -> tuple[SourceCoverage, ...]:
    grouped: dict[str, list[SourceCoverage]] = {}
    for item in values:
        grouped.setdefault(item.source, []).append(item)
    aggregated: list[SourceCoverage] = []
    for source, items in grouped.items():
        statuses = {item.status for item in items}
        status = (
            SourceCoverageStatus.COMPLETE
            if statuses == {SourceCoverageStatus.COMPLETE}
            else SourceCoverageStatus.UNAVAILABLE
            if statuses == {SourceCoverageStatus.UNAVAILABLE}
            else SourceCoverageStatus.DEGRADED
        )
        details = list(dict.fromkeys(item.detail for item in items if item.detail))
        modes = {item.mode for item in items}
        aggregated.append(
            SourceCoverage(
                source=source,
                status=status,
                detail="; ".join(details) if details else None,
                mode=next(iter(modes)) if len(modes) == 1 else None,
            )
        )
    return tuple(aggregated)


def _json_object(content: str, path: str) -> Mapping[str, object]:
    try:
        value = cast(object, json.loads(content))
    except json.JSONDecodeError as error:
        raise ValueError(f"source artifact must contain valid JSON: {path}") from error
    if not isinstance(value, Mapping):
        raise ValueError(f"source artifact must be a JSON object: {path}")
    return {str(key): item for key, item in cast("Mapping[object, object]", value).items()}


def _parse_coverage(payload: Mapping[str, object], path: str) -> tuple[SourceCoverage, ...]:
    raw = payload.get("coverage", payload.get("source_coverage"))
    values: Sequence[object]
    if isinstance(raw, Mapping):
        values = (cast(object, raw),)
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        values = cast("Sequence[object]", raw)
    else:
        raise ValueError(f"source artifact must declare explicit coverage: {path}")
    parsed: list[SourceCoverage] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise ValueError(f"source artifact coverage must be an object: {path}")
        item = cast("Mapping[object, object]", value)
        source = _text(item.get("source"), "coverage source", path)
        status = SourceCoverageStatus(_text(item.get("status"), "coverage status", path))
        detail = _optional_text(item.get("detail"), "coverage detail", path)
        mode_value = item.get("mode")
        parsed.append(
            SourceCoverage(
                source=source,
                status=status,
                detail=detail,
                mode=SourceMode(_text(mode_value, "coverage mode", path))
                if mode_value is not None
                else None,
            )
        )
    if not parsed:
        raise ValueError(f"source artifact must declare explicit coverage: {path}")
    return tuple(parsed)


def _parse_evidence(payload: Mapping[str, object], path: str) -> tuple[tuple[str, Evidence], ...]:
    raw = payload.get("evidence")
    if not isinstance(raw, list):
        raise ValueError(f"source artifact must retain complete provenance: {path}")
    parsed: list[tuple[str, Evidence]] = []
    for value in cast("list[object]", raw):
        if not isinstance(value, Mapping):
            raise ValueError(f"source artifact must retain complete provenance: {path}")
        item = cast("Mapping[object, object]", value)
        raw_provenance = item.get("provenance")
        if not isinstance(raw_provenance, Mapping):
            raise ValueError(f"source artifact must retain complete provenance: {path}")
        provenance = cast("Mapping[object, object]", raw_provenance)
        normalized = {
            "source": _text(provenance.get("source"), "evidence source", path),
            "mode": _text(provenance.get("mode"), "evidence mode", path),
            "endpoint_or_artifact": _text(
                provenance.get("endpoint_or_artifact"), "evidence artifact", path
            ),
            "retrieved_at": _text(provenance.get("retrieved_at"), "retrieval time", path),
            "evidence_location": _text(
                provenance.get("evidence_location"), "evidence location", path
            ),
            "source_version": _text(provenance.get("source_version"), "source version", path),
        }
        citation_id = evidence_citation_id(normalized)
        supplied_id = item.get("citation_id")
        if not isinstance(supplied_id, str) or supplied_id != citation_id:
            raise ValueError(f"source artifact citation id does not match provenance: {path}")
        parsed.append(
            (
                citation_id,
                Evidence(
                    claim=_text(item.get("claim"), "evidence claim", path),
                    provenance=Provenance(
                        source=normalized["source"],
                        mode=SourceMode(normalized["mode"]),
                        endpoint_or_artifact=normalized["endpoint_or_artifact"],
                        retrieved_at=datetime.fromisoformat(normalized["retrieved_at"]),
                        evidence_location=normalized["evidence_location"],
                        source_version=normalized["source_version"],
                    ),
                ),
            )
        )
    return tuple(parsed)


def _text(value: object, field: str, path: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise ValueError(f"source artifact has invalid {field}: {path}")
    text = value.strip()
    if any(ord(char) < 32 and char not in "\t\n\r" for char in text):
        raise ValueError(f"source artifact has invalid {field}: {path}")
    return text


def _optional_text(value: object, field: str, path: str) -> str | None:
    return None if value is None else _text(value, field, path)
