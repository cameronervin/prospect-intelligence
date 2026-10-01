"""Canonical JSON validation for the reviewed regression snapshot."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from hashlib import sha256
from typing import cast

from app.features.agent_quality.public import REGRESSION_DATASET_VERSION

_ROW_KEYS = frozenset(
    {
        "version",
        "split",
        "candidate_id",
        "example_id",
        "signature",
        "inputs",
        "reference_outputs",
        "metadata",
        "checksum",
        "promoted_at",
    }
)
_INPUT_KEYS = frozenset({"example_id", "account_id", "account_name", "input_payload"})
_REFERENCE_KEYS = frozenset(
    {
        "input_payload",
        "expected_top_lanes",
        "expected_verdict",
        "expected_next_step",
        "expected_lane_scores",
        "injection_canary",
    }
)
_METADATA_KEYS = frozenset(
    {
        "failure_type",
        "source_kind",
        "source_run_id",
        "source_event_id",
        "evidence",
        "versions",
        "reviewer",
        "reviewed_at",
    }
)
_VERSION_KEYS = frozenset(
    {"agent_version", "prompt_version", "graph_revision", "evaluator_version"}
)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()


def _sha256(value: object) -> str:
    return sha256(_canonical_json(value)).hexdigest()


def _object(value: object, *, field: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"regression {field} must be an object")
    return {str(key): item for key, item in cast("Mapping[object, object]", value).items()}


def _exact_keys(payload: Mapping[str, object], expected: frozenset[str], *, field: str) -> None:
    if set(payload) != set(expected):
        raise ValueError(f"regression {field} fields are invalid")


def _required_text(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"regression {field} must be a non-empty string")
    return value


def _hex_digest(payload: Mapping[str, object], field: str) -> str:
    value = _required_text(payload, field)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"regression {field} must be a lowercase SHA-256 digest")
    return value


def _timestamp(payload: Mapping[str, object], field: str) -> None:
    value = _required_text(payload, field)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"regression {field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"regression {field} must include a timezone")


def _validate_row(raw: Mapping[str, object]) -> dict[str, object]:
    row = dict(raw)
    _exact_keys(row, _ROW_KEYS, field="example")
    if row["version"] != REGRESSION_DATASET_VERSION or row["split"] != "regression":
        raise ValueError("regression example version or split is invalid")
    candidate_id = _required_text(row, "candidate_id")
    example_id = _required_text(row, "example_id")
    _hex_digest(row, "signature")
    expected_checksum = _hex_digest(row, "checksum")
    _timestamp(row, "promoted_at")

    inputs = _object(row["inputs"], field="inputs")
    _exact_keys(inputs, _INPUT_KEYS, field="inputs")
    for field in ("example_id", "account_id", "account_name"):
        _required_text(inputs, field)
    if inputs["example_id"] != example_id:
        raise ValueError("regression input example_id does not match its row")
    _object(inputs["input_payload"], field="input_payload")

    references = _object(row["reference_outputs"], field="reference_outputs")
    _exact_keys(references, _REFERENCE_KEYS, field="reference_outputs")
    _object(references["input_payload"], field="reference input_payload")
    for field in ("expected_top_lanes", "expected_lane_scores"):
        if not isinstance(references[field], list):
            raise ValueError(f"regression reference {field} must be a list")
    for field in ("expected_verdict", "expected_next_step"):
        _required_text(references, field)
    canary = references["injection_canary"]
    if canary is not None and not isinstance(canary, str):
        raise ValueError("regression reference injection_canary must be a string or null")

    metadata = _object(row["metadata"], field="metadata")
    _exact_keys(metadata, _METADATA_KEYS, field="metadata")
    for field in (
        "failure_type",
        "source_kind",
        "source_run_id",
        "source_event_id",
        "reviewer",
    ):
        _required_text(metadata, field)
    if metadata["source_kind"] not in {"online_flag", "rep_rejection"}:
        raise ValueError("regression source_kind is invalid")
    _timestamp(metadata, "reviewed_at")
    _object(metadata["evidence"], field="evidence")
    versions = _object(metadata["versions"], field="versions")
    _exact_keys(versions, _VERSION_KEYS, field="versions")
    if any(not isinstance(value, str) or not value.strip() for value in versions.values()):
        raise ValueError("regression versions must contain non-empty strings")

    unsigned = {key: value for key, value in row.items() if key != "checksum"}
    if _sha256(unsigned) != expected_checksum:
        raise ValueError(f"regression row checksum mismatch: {candidate_id}")
    return row


def canonical_regression_snapshot_bytes(examples: Sequence[Mapping[str, object]]) -> bytes:
    """Return the stable checked snapshot representation used by promotion exports."""

    rows: list[dict[str, object]] = sorted(
        (_validate_row(row) for row in examples),
        key=lambda row: cast(str, row["example_id"]),
    )
    for field in ("candidate_id", "example_id", "signature"):
        values = [cast(str, row[field]) for row in rows]
        if len(set(values)) != len(values):
            raise ValueError(f"regression snapshot contains duplicate {field}")
    unsigned = {"dataset_version": REGRESSION_DATASET_VERSION, "examples": rows}
    payload = {**unsigned, "checksum": _sha256(unsigned)}
    return (
        json.dumps(payload, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def decode_regression_snapshot(raw: bytes) -> tuple[dict[str, object], ...]:
    """Decode a canonical snapshot and fail closed on integrity or schema drift."""

    def reject_constant(value: str) -> None:
        raise ValueError(f"regression snapshot contains non-finite number: {value}")

    try:
        payload = _object(json.loads(raw, parse_constant=reject_constant), field="snapshot")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("regression snapshot is not valid JSON") from error
    _exact_keys(payload, frozenset({"dataset_version", "examples", "checksum"}), field="snapshot")
    if payload["dataset_version"] != REGRESSION_DATASET_VERSION:
        raise ValueError("regression snapshot dataset version is invalid")
    raw_rows = payload["examples"]
    if not isinstance(raw_rows, list):
        raise ValueError("regression snapshot examples must be a list")
    rows = tuple(
        _validate_row(_object(row, field="example")) for row in cast("list[object]", raw_rows)
    )
    unsigned = {"dataset_version": REGRESSION_DATASET_VERSION, "examples": list(rows)}
    if _sha256(unsigned) != _hex_digest(payload, "checksum"):
        raise ValueError("regression snapshot checksum mismatch")
    if raw != canonical_regression_snapshot_bytes(rows):
        raise ValueError("regression snapshot is not canonical")
    return rows
