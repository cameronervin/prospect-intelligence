"""Stable opaque citation identifiers for prospect evidence records."""

import hashlib
import json
from collections.abc import Mapping

_PROVENANCE_FIELDS = (
    "source",
    "mode",
    "endpoint_or_artifact",
    "retrieved_at",
    "evidence_location",
    "source_version",
)


def evidence_citation_id(provenance: Mapping[str, object]) -> str:
    canonical: dict[str, str] = {}
    for field in _PROVENANCE_FIELDS:
        value = provenance.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 512:
            raise ValueError("evidence provenance is invalid")
        canonical[field] = value.strip()
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return f"ev_{hashlib.sha256(encoded).hexdigest()[:24]}"
