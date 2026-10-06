"""Canonical serialization for normalized source results and typed artifact tools."""

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import cast
from uuid import UUID

from .citations import evidence_citation_id
from .models import Evidence


def canonical_source_document(result: object) -> dict[str, object]:
    """Serialize one normalized source result without a model authoring step."""

    safe = _json_safe(result)
    if not isinstance(safe, Mapping):
        raise TypeError("normalized source result must be an object")
    payload = {str(key): value for key, value in cast("Mapping[object, object]", safe).items()}
    if not isinstance(payload.get("coverage"), Mapping) or not isinstance(
        payload.get("evidence"), list
    ):
        raise TypeError("normalized source result must contain coverage and evidence")
    return payload


def canonical_source_json(result: object) -> str:
    return canonical_json(canonical_source_document(result))


def normalized_json(result: object) -> str:
    """Serialize an internal normalized value for legacy read-only tool consumers."""

    return json.dumps(
        _json_safe(result),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def combined_source_document(results: Sequence[object]) -> dict[str, object]:
    documents = [canonical_source_document(result) for result in results]
    return {
        "coverage": [document["coverage"] for document in documents],
        "evidence": [
            evidence
            for document in documents
            for evidence in cast("list[object]", document["evidence"])
        ],
    }


def market_source_document(results: Sequence[tuple[str, object]]) -> dict[str, object]:
    documents = [(key, canonical_source_document(result)) for key, result in results]
    return {
        "sources": {key: document.get("value") for key, document in documents},
        "coverage": [document["coverage"] for _, document in documents],
        "evidence": [
            evidence
            for _, document in documents
            for evidence in cast("list[object]", document["evidence"])
        ],
    }


def canonical_json(payload: Mapping[str, object]) -> str:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _json_safe(value: object) -> object:
    if isinstance(value, Evidence):
        safe_provenance = cast("Mapping[str, object]", _json_safe(value.provenance))
        return {
            "claim": value.claim,
            "citation_id": evidence_citation_id(safe_provenance),
            "provenance": safe_provenance,
        }
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe({field.name: getattr(value, field.name) for field in fields(value)})
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in cast("Mapping[object, object]", value).items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in cast("Iterable[object]", value)]
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"source result contains unsupported value: {type(value).__name__}")
