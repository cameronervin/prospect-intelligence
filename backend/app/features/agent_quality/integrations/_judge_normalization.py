"""Strict provider-response normalization without retaining provider payloads."""

import math
from collections.abc import Mapping
from typing import cast

from typesafe_sdk import Choice, Noul, Score

from app.features.agent_quality.contracts.semantic_judges import (
    CertaintySource,
    DecisionValue,
    JudgeDecision,
    JudgeProtocolError,
    ResolvedModelSource,
    RetryCountSource,
    SemanticQuestion,
    TokenCountSource,
    TokenPricing,
    state_sha256,
)


def attribute(value: object, name: str) -> object:
    try:
        return getattr(value, name)
    except (AttributeError, TypeError) as error:
        raise JudgeProtocolError(f"provider response is missing {name}") from error


def _probability(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JudgeProtocolError(f"{field} must be a finite probability")
    result = float(value)
    if not math.isfinite(result):
        raise JudgeProtocolError(f"{field} must be finite")
    if not 0 <= result <= 1:
        raise JudgeProtocolError(f"{field} must be between 0 and 1")
    return result


def _tokens(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise JudgeProtocolError(f"{field} must be a non-negative integer or null")
    return value


def _distribution(raw: object, expected: tuple[str, ...]) -> dict[str, float]:
    if not isinstance(raw, Mapping):
        raise JudgeProtocolError("probabilities must be a mapping")
    normalized = {
        str(key): _probability(value, "probability")
        for key, value in cast("Mapping[object, object]", raw).items()
    }
    if set(normalized) != set(expected):
        raise JudgeProtocolError("probability options do not match the requested options")
    if not math.isclose(sum(normalized.values()), 1.0, abs_tol=0.01):
        raise JudgeProtocolError("probabilities must sum to one")
    return {key: normalized[key] for key in expected}


def _request_id(response: object) -> str | None:
    try:
        value = response.__getattribute__("request_id")
    except Exception:  # The comparison adapter has no TypeSafe HTTP response.
        return None
    return value if isinstance(value, str) and value else None


def _retry_count(
    response: object, observed_retries: int | None
) -> tuple[int | None, RetryCountSource]:
    if observed_retries is not None:
        return observed_retries, "sdk_policy"
    usage = getattr(response, "usage", None)
    adapter_retries = getattr(usage, "n_retries", None)
    malformed_retries = getattr(usage, "n_retries_malformed_structure", 0)
    if isinstance(adapter_retries, int) and adapter_retries >= 0:
        valid_malformed = (
            malformed_retries
            if isinstance(malformed_retries, int) and malformed_retries >= 0
            else 0
        )
        return adapter_retries + valid_malformed, "provider_usage"
    return None, "unavailable"


def _cost(
    pricing: TokenPricing,
    input_tokens: int | None,
    cached_tokens: int | None,
    output_tokens: int | None,
) -> float | None:
    if input_tokens is None or (output_tokens is None and pricing.output_usd_per_million > 0):
        return None
    output = output_tokens or 0
    cached = cached_tokens or 0
    if cached > input_tokens:
        raise JudgeProtocolError("cached_input_tokens cannot exceed input_tokens")
    uncached = input_tokens - cached
    return (
        uncached * pricing.input_usd_per_million
        + cached * pricing.cached_input_usd_per_million
        + output * pricing.output_usd_per_million
    ) / 1_000_000


def question_payload(question: SemanticQuestion, option_order: tuple[str, ...]):
    if question.kind == "noul":
        return Noul(
            instructions=question.instructions,
            criteria={"true": question.true_criterion, "false": question.false_criterion},
        )
    if question.kind == "choice":
        descriptions = dict(zip(question.options, question.criteria, strict=True))
        return Choice(
            instructions=question.instructions,
            criteria={option: descriptions[option] for option in option_order},
        )
    descriptions = dict(zip(question.options, question.criteria, strict=True))
    return Score(
        instructions=question.instructions,
        criteria=tuple(descriptions[option] for option in option_order),
    )


def _answer(
    question: SemanticQuestion, order: tuple[str, ...], answer: object
) -> tuple[DecisionValue, dict[str, float], float, CertaintySource]:
    if question.kind == "noul":
        yes = _probability(attribute(answer, "noul"), "noul")
        return (
            yes >= 0.5,
            {"yes": yes, "no": 1 - yes},
            2 * abs(yes - 0.5),
            "derived_noul_probability",
        )
    certainty = _probability(attribute(answer, "confidence"), "confidence")
    if question.kind == "choice":
        probabilities = _distribution(attribute(answer, "probabilities"), order)
        choice = attribute(answer, "choice")
        if not isinstance(choice, str) or choice not in order:
            raise JudgeProtocolError("choice must be one of the requested options")
        return choice, probabilities, certainty, "provider_confidence"
    raw_score = attribute(answer, "score")
    if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
        raise JudgeProtocolError("score must be finite")
    score = float(raw_score)
    if not math.isfinite(score):
        raise JudgeProtocolError("score must be finite")
    if not 0 <= score <= len(question.criteria) - 1:
        raise JudgeProtocolError("score is outside the requested rubric")
    zero_based = tuple(str(index) for index in range(len(question.criteria)))
    raw_probabilities = _distribution(attribute(answer, "probabilities"), zero_based)
    probability_total = sum(raw_probabilities.values())
    normalized = {
        position: probability / probability_total
        for position, probability in raw_probabilities.items()
    }
    probabilities = {option: raw_probabilities[str(index)] for index, option in enumerate(order)}
    canonical_probabilities = {option: probabilities[option] for option in question.options}
    try:
        canonical_score = sum(
            float(option) * normalized[str(index)] for index, option in enumerate(order)
        )
    except ValueError as error:
        raise JudgeProtocolError("score options must be numeric") from error
    return canonical_score, canonical_probabilities, certainty, "provider_confidence"


def normalize_response(
    *,
    question: SemanticQuestion,
    state: Mapping[str, object],
    option_order: tuple[str, ...],
    response: object,
    requested_model: str,
    rubric_version: str,
    pricing: TokenPricing,
    resolved_model_source: ResolvedModelSource,
    observed_retries: int | None,
    latency_seconds: float,
) -> JudgeDecision:
    resolved_model = attribute(response, "model")
    if not isinstance(resolved_model, str) or resolved_model != requested_model:
        raise JudgeProtocolError(
            f"provider resolved model {resolved_model!r}, expected {requested_model!r}"
        )
    raw_answers = attribute(response, "answers")
    if not isinstance(raw_answers, Mapping):
        raise JudgeProtocolError("provider response must contain exactly the decision answer")
    answers = cast("Mapping[object, object]", raw_answers)
    if set(answers) != {"decision"}:
        raise JudgeProtocolError("provider response must contain exactly the decision answer")
    answer = answers["decision"]
    answer_type = attribute(answer, "type")
    if answer_type != question.kind:
        raise JudgeProtocolError(
            f"provider answer type {answer_type!r} does not match {question.kind!r}"
        )
    value, probabilities, certainty, source = _answer(question, option_order, answer)
    usage = attribute(response, "usage")
    final_input = _tokens(attribute(usage, "input_tokens"), "input_tokens")
    final_output = _tokens(attribute(usage, "output_tokens"), "output_tokens")
    total_input = _tokens(getattr(usage, "input_tokens_total", None), "input_tokens_total")
    total_output = _tokens(getattr(usage, "output_tokens_total", None), "output_tokens_total")
    uses_totals = total_input is not None or total_output is not None
    input_tokens = total_input if total_input is not None else final_input
    output_tokens = total_output if total_output is not None else final_output
    token_count_source: TokenCountSource = "provider_total" if uses_totals else "provider_final"
    cached_tokens = (
        None
        if uses_totals
        else _tokens(getattr(usage, "cached_input_tokens", None), "cached_input_tokens")
    )
    retries, retry_count_source = _retry_count(response, observed_retries)
    return JudgeDecision(
        question_key=question.key,
        rubric_version=rubric_version,
        value=value,
        probabilities=probabilities,
        certainty=certainty,
        certainty_source=source,
        requested_model=requested_model,
        resolved_model=resolved_model,
        resolved_model_source=resolved_model_source,
        option_order=option_order,
        state_hash=state_sha256(state),
        latency_seconds=latency_seconds,
        request_id=_request_id(response),
        input_tokens=input_tokens,
        cached_input_tokens=cached_tokens,
        output_tokens=output_tokens,
        token_count_source=token_count_source,
        retries=retries,
        retry_count_source=retry_count_source,
        pricing_version=pricing.version,
        estimated_cost_usd=_cost(pricing, input_tokens, cached_tokens, output_tokens),
    )
