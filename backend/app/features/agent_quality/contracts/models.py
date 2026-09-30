"""Sanitized inputs and configuration for online evaluation."""

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from .sampling import EvaluationSamplingDecision


def _empty_metadata() -> dict[str, object]:
    return {}


@dataclass(frozen=True, slots=True)
class QualitySignal:
    key: str
    score: float | None
    passed: bool | None
    comment: str | None = None
    value: bool | str | float | None = None
    scale_min: float = 0.0
    scale_max: float = 1.0
    metadata: Mapping[str, object] = field(default_factory=_empty_metadata)

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("quality signal key must be non-empty")
        if (
            not math.isfinite(self.scale_min)
            or not math.isfinite(self.scale_max)
            or self.scale_min >= self.scale_max
        ):
            raise ValueError("quality signal scale must be finite and increasing")
        if self.score is not None and not self.scale_min <= self.score <= self.scale_max:
            raise ValueError("quality signal score must be within its configured scale")

    def to_payload(self) -> dict[str, object]:
        return {
            "key": self.key,
            "score": self.score,
            "passed": self.passed,
            "value": self.value,
            "scale_min": self.scale_min,
            "scale_max": self.scale_max,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "QualitySignal":
        score = payload.get("score")
        passed = payload.get("passed")
        value = payload.get("value")
        metadata = payload.get("metadata", {})
        if score is not None and (isinstance(score, bool) or not isinstance(score, int | float)):
            raise ValueError("quality signal score must be numeric or null")
        if passed is not None and not isinstance(passed, bool):
            raise ValueError("quality signal passed must be boolean or null")
        if value is not None and not isinstance(value, bool | str | int | float):
            raise ValueError("quality signal value must be scalar or null")
        if not isinstance(metadata, Mapping):
            raise ValueError("quality signal metadata must be an object")
        return cls(
            key=_payload_string(payload, "key"),
            score=float(score) if score is not None else None,
            passed=passed,
            value=value,
            scale_min=_payload_number(payload, "scale_min"),
            scale_max=_payload_number(payload, "scale_max"),
            metadata=dict(cast("Mapping[str, object]", metadata)),
        )


@dataclass(frozen=True, slots=True)
class SemanticEvaluationInput:
    """One criterion-specific state permitted to reach a semantic judge."""

    key: str
    state: Mapping[str, object]
    instance_id: str = "default"
    expected_value: str | None = None
    not_applicable: bool = False

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("semantic evaluation key must be non-empty")
        if not self.instance_id.strip():
            raise ValueError("semantic evaluation instance_id must be non-empty")
        if self.expected_value is not None and not self.expected_value.strip():
            raise ValueError("semantic evaluation expected_value must be non-empty")
        _bounded_json(self.state, name="semantic evaluation state", maximum=32_768)

    def to_payload(self) -> dict[str, object]:
        return {
            "key": self.key,
            "instance_id": self.instance_id,
            "state": dict(self.state),
            "expected_value": self.expected_value,
            "not_applicable": self.not_applicable,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "SemanticEvaluationInput":
        state = payload.get("state")
        if not isinstance(state, Mapping):
            raise ValueError("semantic evaluation state must be an object")
        expected_value = payload.get("expected_value")
        not_applicable = payload.get("not_applicable", False)
        if expected_value is not None and not isinstance(expected_value, str):
            raise ValueError("semantic evaluation expected_value must be text or null")
        if not isinstance(not_applicable, bool):
            raise ValueError("semantic evaluation not_applicable must be boolean")
        return cls(
            key=_payload_string(payload, "key"),
            instance_id=_payload_string(payload, "instance_id"),
            state=dict(cast("Mapping[str, object]", state)),
            expected_value=expected_value,
            not_applicable=not_applicable,
        )


@dataclass(frozen=True, slots=True)
class QualityEvaluationEnvelope:
    """Durable bounded evaluator input stored separately from provider event metadata."""

    evaluator_version: str
    graph_revision: str
    rubric_version: str
    agent_version: str = "prospect-intelligence-v1"
    prompt_version: str = "v1"
    deterministic_signals: tuple[QualitySignal, ...] = ()
    semantic_inputs: tuple[SemanticEvaluationInput, ...] = ()

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.evaluator_version,
                self.graph_revision,
                self.rubric_version,
                self.agent_version,
                self.prompt_version,
            )
        ):
            raise ValueError("evaluation envelope versions must be non-empty")
        keys = [(item.key, item.instance_id) for item in self.semantic_inputs]
        if len(keys) != len(set(keys)):
            raise ValueError("semantic evaluation keys must be unique")
        _bounded_json(self.to_payload(), name="evaluation envelope", maximum=131_072)

    def to_payload(self) -> dict[str, object]:
        return {
            "evaluator_version": self.evaluator_version,
            "graph_revision": self.graph_revision,
            "rubric_version": self.rubric_version,
            "agent_version": self.agent_version,
            "prompt_version": self.prompt_version,
            "deterministic_signals": [item.to_payload() for item in self.deterministic_signals],
            "semantic_inputs": [item.to_payload() for item in self.semantic_inputs],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "QualityEvaluationEnvelope":
        raw_signals = _payload_mappings(payload, "deterministic_signals")
        raw_inputs = _payload_mappings(payload, "semantic_inputs")
        return cls(
            evaluator_version=_payload_string(payload, "evaluator_version"),
            graph_revision=_payload_string(payload, "graph_revision"),
            rubric_version=_payload_string(payload, "rubric_version"),
            agent_version=_payload_string_or_default(
                payload, "agent_version", "prospect-intelligence-v1"
            ),
            prompt_version=_payload_string_or_default(payload, "prompt_version", "v1"),
            deterministic_signals=tuple(QualitySignal.from_payload(item) for item in raw_signals),
            semantic_inputs=tuple(
                SemanticEvaluationInput.from_payload(item) for item in raw_inputs
            ),
        )


@dataclass(frozen=True, slots=True)
class QualityEvaluationProjection:
    """A durable sampling decision and its optional bounded evaluator input."""

    sampling: EvaluationSamplingDecision
    evaluation: QualityEvaluationEnvelope | None

    def __post_init__(self) -> None:
        if self.sampling.selected is not (self.evaluation is not None):
            raise ValueError(
                "selected evaluation sampling requires exactly one evaluation envelope"
            )


def _bounded_json(value: object, *, name: str, maximum: int) -> None:
    try:
        encoded = json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be finite JSON") from error
    if len(encoded.encode()) > maximum:
        raise ValueError(f"{name} exceeds {maximum} bytes")


def _payload_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"evaluation payload has invalid {key}")
    return value


def _payload_string_or_default(payload: Mapping[str, object], key: str, default: str) -> str:
    value = payload.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"evaluation payload has invalid {key}")
    return value


def _payload_number(payload: Mapping[str, object], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"evaluation payload has invalid {key}")
    return float(value)


def _payload_mappings(payload: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"evaluation payload has invalid {key}")
    items = cast("list[object]", value)
    if any(not isinstance(item, Mapping) for item in items):
        raise ValueError("evaluation envelope entries must be objects")
    return [cast("Mapping[str, object]", item) for item in items]
