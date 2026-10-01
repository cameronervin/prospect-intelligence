"""Sanitized payload boundary for reviewed regression candidates."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import cast

_MAX_DRAFT_BYTES = 262_144
_MACHINE_KEY = re.compile(r"^[a-z][a-z0-9_:-]{0,99}$")
_REQUIRED_INPUT_KEYS: set[str] = {"account_id", "account_name", "input_payload"}
_REQUIRED_REFERENCE_KEYS: set[str] = {
    "input_payload",
    "expected_top_lanes",
    "expected_verdict",
    "expected_next_step",
    "expected_lane_scores",
    "injection_canary",
}
_REQUIRED_VERSION_KEYS: set[str] = {
    "agent_version",
    "prompt_version",
    "graph_revision",
    "evaluator_version",
}
_FORBIDDEN_KEYS = frozenset(
    {
        "authorization",
        "actor_scope",
        "contact",
        "credentials",
        "email",
        "messages",
        "phone",
        "prompt",
        "provider_payload",
        "raw_trace",
        "rep_id",
        "tenant_id",
        "trace",
    }
)
_FORBIDDEN_NORMALIZED_KEYS = frozenset(re.sub(r"[^a-z0-9]", "", key) for key in _FORBIDDEN_KEYS)
_TARGET_PAYLOAD_KEYS = frozenset({"crm", "genlogs", "carrier_network", "faf_market"})
_FIT_VERDICTS = frozenset({"fit", "no_fit", "needs_more_data"})
_NEXT_STEPS = frozenset({"expand_existing_lanes", "new_lane_pitch", "not_a_fit", "needs_more_data"})


class CandidateSource(StrEnum):
    ONLINE_FLAG = "online_flag"
    REP_REJECTION = "rep_rejection"


def canonical_regression_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("regression candidate must contain finite JSON") from error


def copy_json_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return cast("dict[str, object]", json.loads(canonical_regression_bytes(value)))


def _validate_no_forbidden_keys(value: object, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        for raw_key, item in mapping.items():
            if not isinstance(raw_key, str):
                raise ValueError("regression candidate JSON keys must be strings")
            key = re.sub(r"[^a-z0-9]", "", raw_key.casefold())
            if key in _FORBIDDEN_NORMALIZED_KEYS:
                raise ValueError(f"regression candidate contains forbidden field: {path}.{raw_key}")
            _validate_no_forbidden_keys(item, path=f"{path}.{raw_key}")
    elif isinstance(value, list | tuple):
        sequence = cast("list[object] | tuple[object, ...]", value)
        for index, item in enumerate(sequence):
            _validate_no_forbidden_keys(item, path=f"{path}[{index}]")


def require_machine_key(value: str, *, name: str) -> None:
    if _MACHINE_KEY.fullmatch(value) is None:
        raise ValueError(f"{name} must be a sanitized machine-readable key")


def _mapping(value: object, *, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    mapping = cast("Mapping[object, object]", value)
    if any(not isinstance(key, str) for key in mapping):
        raise ValueError(f"{name} keys must be strings")
    return cast("Mapping[str, object]", mapping)


def _text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _list(value: object, *, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return cast("list[object]", value)


def _validate_shared_schema(
    sanitized_input: Mapping[str, object],
    sanitized_reference: Mapping[str, object],
) -> None:
    account_id = _text(sanitized_input["account_id"], name="account_id")
    account_name = _text(sanitized_input["account_name"], name="account_name")
    target = _mapping(sanitized_input["input_payload"], name="input_payload")
    if set(target) != set(_TARGET_PAYLOAD_KEYS):
        raise ValueError("input_payload does not match the shared evaluation schema")
    sources = {
        name: _mapping(target[name], name=f"input_payload.{name}")
        for name in sorted(_TARGET_PAYLOAD_KEYS)
    }
    crm = sources["crm"]
    if _text(crm.get("account_id"), name="input_payload.crm.account_id") != account_id:
        raise ValueError("input_payload CRM account_id does not match target account_id")
    if _text(crm.get("account_name"), name="input_payload.crm.account_name") != account_name:
        raise ValueError("input_payload CRM account_name does not match target account_name")
    for source in ("genlogs", "carrier_network", "faf_market"):
        _list(sources[source].get("lanes"), name=f"input_payload.{source}.lanes")

    reference_payload = _mapping(
        sanitized_reference["input_payload"], name="reference input_payload"
    )
    if canonical_regression_bytes(reference_payload) != canonical_regression_bytes(target):
        raise ValueError("reference input_payload must match the target input_payload")
    _list(sanitized_reference["expected_top_lanes"], name="expected_top_lanes")
    _list(sanitized_reference["expected_lane_scores"], name="expected_lane_scores")
    if sanitized_reference["expected_verdict"] not in _FIT_VERDICTS:
        raise ValueError("expected_verdict is invalid")
    if sanitized_reference["expected_next_step"] not in _NEXT_STEPS:
        raise ValueError("expected_next_step is invalid")
    canary = sanitized_reference["injection_canary"]
    if canary is not None and not isinstance(canary, str):
        raise ValueError("injection_canary must be a string or null")


@dataclass(frozen=True, slots=True)
class RegressionDraft:
    source_kind: CandidateSource
    source_run_id: str
    source_event_id: str
    failure_type: str
    sanitized_input: Mapping[str, object]
    sanitized_reference: Mapping[str, object]
    evidence: Mapping[str, object]
    versions: Mapping[str, str]

    def with_evidence(self, evidence: Mapping[str, object]) -> RegressionDraft:
        return replace(self, evidence=evidence)

    def with_input(self, sanitized_input: Mapping[str, object]) -> RegressionDraft:
        return replace(self, sanitized_input=sanitized_input)

    def validate(self) -> None:
        if not self.source_run_id.strip() or not self.source_event_id.strip():
            raise ValueError("regression source identifiers must be non-empty")
        require_machine_key(self.failure_type, name="failure_type")
        if set(self.sanitized_input) != _REQUIRED_INPUT_KEYS:
            raise ValueError("sanitized input does not match the shared evaluation schema")
        if set(self.sanitized_reference) != _REQUIRED_REFERENCE_KEYS:
            raise ValueError("sanitized reference does not match the shared evaluation schema")
        if set(self.versions) != _REQUIRED_VERSION_KEYS or any(
            not value.strip() for value in self.versions.values()
        ):
            raise ValueError("regression version provenance is incomplete")
        for payload in (self.sanitized_input, self.sanitized_reference, self.evidence):
            _validate_no_forbidden_keys(payload)
        _validate_shared_schema(self.sanitized_input, self.sanitized_reference)
        encoded = canonical_regression_bytes(
            {
                "input": self.sanitized_input,
                "reference": self.sanitized_reference,
                "evidence": self.evidence,
                "versions": self.versions,
            }
        )
        if len(encoded) > _MAX_DRAFT_BYTES:
            raise ValueError(f"regression candidate exceeds {_MAX_DRAFT_BYTES} bytes")

    @property
    def signature(self) -> str:
        self.validate()
        return hashlib.sha256(
            canonical_regression_bytes(
                {"failure_type": self.failure_type, "input": self.sanitized_input}
            )
        ).hexdigest()
