"""Sanitization helpers for LangSmith event publication."""

import hashlib
import re
from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from app.features.agent_quality.contracts.models import QualitySignal

EVENT_INPUT_KEYS = (
    "account_id",
    "tenant_id_hash",
    "rep_id_hash",
    "event_type",
    "occurred_at",
    "agent_version",
    "prompt_version",
    "verdict",
    "review_decision",
    "edit_distance",
    "source_modes",
    "error_code",
    "evaluation_sampled",
    "evaluation_sample_rate",
    "evaluation_sampling_policy",
)

_SAFE_FEEDBACK_METADATA_KEYS = (
    "evaluator_version",
    "graph_revision",
    "rubric_version",
    "agent_version",
    "prompt_version",
    "requested_model",
    "resolved_model",
    "state_hash",
    "latency_seconds",
    "estimated_cost_usd",
    "status",
    "instance_count",
)
_EVENT_METADATA_KEYS = (
    "agent_version",
    "simulated",
    "simulator_version",
    "traffic_pool_version",
    "simulation_session_index",
)


def required_uuid(payload: Mapping[str, object], key: str) -> UUID:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"quality event {key} must be a UUID string")
    try:
        return UUID(value)
    except ValueError as error:
        raise ValueError(f"quality event {key} must be a UUID string") from error


def external_account_id(account_id: str) -> str:
    synthetic = re.fullmatch(r"syn_(?:core|edge|traffic|live)_\d{2}", account_id) is not None
    return account_id if synthetic else hashlib.sha256(account_id.encode()).hexdigest()


def required_datetime(payload: Mapping[str, object], key: str) -> datetime:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"quality event {key} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"quality event {key} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"quality event {key} must include a timezone")
    return parsed


def feedback_source_info(signal: QualitySignal) -> dict[str, object]:
    """Allow only bounded evaluator scale metadata, never raw judge state."""

    result: dict[str, object] = {}
    scale_min = getattr(signal, "scale_min", None)
    scale_max = getattr(signal, "scale_max", None)
    if isinstance(scale_min, int | float):
        result["scale_min"] = scale_min
    if isinstance(scale_max, int | float):
        result["scale_max"] = scale_max
    for key in _SAFE_FEEDBACK_METADATA_KEYS:
        value = signal.metadata.get(key)
        if value is not None and isinstance(value, bool | str | int | float):
            result[key] = value
    return result


def event_metadata(payload: Mapping[str, object]) -> dict[str, bool | int | str]:
    """Project only bounded operational dimensions used by LangSmith charts."""

    metadata: dict[str, bool | int | str] = {}
    for key in _EVENT_METADATA_KEYS:
        value = payload.get(key)
        if value is None:
            continue
        if key == "simulated":
            if not isinstance(value, bool):
                raise ValueError("quality event simulated must be boolean")
        elif key == "simulation_session_index":
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10_000:
                raise ValueError("quality event simulation session index is invalid")
        elif not isinstance(value, str) or not value.strip() or len(value) > 128:
            raise ValueError(f"quality event {key.replace('_', ' ')} is invalid")
        metadata[key] = value
    return metadata


def event_tags(metadata: Mapping[str, bool | int | str]) -> list[str]:
    if metadata.get("simulated") is not True:
        return []
    tags = ["traffic_simulator"]
    pool_version = metadata.get("traffic_pool_version")
    if isinstance(pool_version, str):
        tags.append(pool_version)
    return tags
