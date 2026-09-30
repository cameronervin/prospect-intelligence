"""Provider-neutral contracts and bounded state for semantic judges."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, cast, runtime_checkable

JUDGE_TIMEOUT_SECONDS = 30.0
JUDGE_MAX_RETRIES = 2
MAX_STATE_BYTES = 32_768
MAX_STATE_STRING_CHARS = 8_000

QuestionKind = Literal["noul", "choice", "score"]
DecisionValue = bool | str | float
CertaintySource = Literal["derived_noul_probability", "provider_confidence"]
RetryCountSource = Literal["sdk_policy", "provider_usage", "unavailable"]
ResolvedModelSource = Literal["provider_response", "adapter_configuration"]
TokenCountSource = Literal["provider_final", "provider_total"]


@dataclass(frozen=True, slots=True)
class SemanticQuestion:
    key: str
    kind: QuestionKind
    instructions: str
    state_fields: tuple[str, ...]
    options: tuple[str, ...] = ()
    criteria: tuple[str, ...] = ()
    true_criterion: str | None = None
    false_criterion: str | None = None


@dataclass(frozen=True, slots=True)
class JudgeDecision:
    """Provider-neutral semantic result safe to attach to evaluation metadata."""

    question_key: str
    rubric_version: str
    value: DecisionValue
    probabilities: Mapping[str, float]
    certainty: float
    certainty_source: CertaintySource
    requested_model: str
    resolved_model: str
    resolved_model_source: ResolvedModelSource
    option_order: tuple[str, ...]
    state_hash: str
    latency_seconds: float
    request_id: str | None
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    token_count_source: TokenCountSource
    retries: int | None
    retry_count_source: RetryCountSource
    pricing_version: str
    estimated_cost_usd: float | None


@dataclass(frozen=True, slots=True)
class TokenPricing:
    """Versioned standard token rates used only for cost estimation."""

    version: str
    input_usd_per_million: float
    cached_input_usd_per_million: float
    output_usd_per_million: float


@runtime_checkable
class SemanticJudge(Protocol):
    async def evaluate(
        self,
        question_key: str,
        state: Mapping[str, object],
        *,
        option_order: tuple[str, ...] | None = None,
    ) -> JudgeDecision: ...


class JudgeProtocolError(RuntimeError):
    """A provider returned a response that violates the judge contract."""


def decision_metadata(decision: JudgeDecision) -> dict[str, object]:
    """Return the complete normalized metadata safe for evaluation storage."""

    return {
        "requested_model": decision.requested_model,
        "resolved_model": decision.resolved_model,
        "resolved_model_source": decision.resolved_model_source,
        "rubric_version": decision.rubric_version,
        "option_order": list(decision.option_order),
        "probabilities": dict(decision.probabilities),
        "certainty": decision.certainty,
        "certainty_source": decision.certainty_source,
        "state_hash": decision.state_hash,
        "latency_seconds": decision.latency_seconds,
        "request_id": decision.request_id,
        "input_tokens": decision.input_tokens,
        "cached_input_tokens": decision.cached_input_tokens,
        "output_tokens": decision.output_tokens,
        "token_count_source": decision.token_count_source,
        "retries": decision.retries,
        "retry_count_source": decision.retry_count_source,
        "pricing_version": decision.pricing_version,
        "estimated_cost_usd": decision.estimated_cost_usd,
    }


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("judge state must contain only finite JSON-compatible values") from error


def state_sha256(state: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_json(state).encode()).hexdigest()


def _validate_json_value(value: object) -> None:
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("judge state numbers must be finite")
        return
    if isinstance(value, str):
        if len(value) > MAX_STATE_STRING_CHARS:
            raise ValueError("judge state string exceeds the configured bound")
        return
    if isinstance(value, Mapping):
        for key, child in cast("Mapping[object, object]", value).items():
            if not isinstance(key, str):
                raise ValueError("judge state object keys must be strings")
            _validate_json_value(child)
        return
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for child in cast("Sequence[object]", value):
            _validate_json_value(child)
        return
    raise ValueError("judge state must contain only finite JSON-compatible values")


def project_state(question: SemanticQuestion, state: Mapping[str, object]) -> dict[str, object]:
    missing = [field for field in question.state_fields if field not in state]
    if missing:
        raise ValueError(f"missing state fields: {', '.join(missing)}")
    projected = {field: state[field] for field in question.state_fields}
    _validate_json_value(projected)
    if any(not isinstance(value, str) for value in projected.values()):
        raise ValueError("judge state fields must be text")
    if len(_canonical_json(projected).encode()) > MAX_STATE_BYTES:
        raise ValueError("judge state exceeds the configured byte bound")
    return projected
