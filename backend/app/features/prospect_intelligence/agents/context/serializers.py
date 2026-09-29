"""Small, deterministic serializers for model-visible context."""

import json
from collections.abc import Mapping


def serialize_context(value: Mapping[str, object], tier: str) -> str:
    """Serialize only an already-allowlisted context projection."""

    if tier == "compact":
        compact = {key: value[key] for key in sorted(value)[:8]}
        return json.dumps(compact, sort_keys=True, separators=(",", ":"), default=str)
    if tier in {"full", "json"}:
        return json.dumps(value, sort_keys=True, default=str)
    raise ValueError(f"unknown serialization tier: {tier}")
