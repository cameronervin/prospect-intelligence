"""LangSmith-native adapters for the injected semantic judges."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import cast

from langsmith.evaluation import EvaluationResult

from evaluation.contracts.judges import JudgeDecision, SemanticJudge, decision_metadata
from evaluation.contracts.semantic import valid_citation_id
from evaluation.rubrics import QUESTIONS

type SemanticEvaluator = Callable[
    [Mapping[str, object], Mapping[str, object]], Awaitable[EvaluationResult]
]


def _observations(outputs: Mapping[str, object]) -> Mapping[str, object]:
    value = outputs.get("semantic_observations")
    return cast("Mapping[str, object]", value) if isinstance(value, Mapping) else {}


def _guard(key: str, evaluator: SemanticEvaluator) -> SemanticEvaluator:
    async def guarded(
        outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
    ) -> EvaluationResult:
        canary = reference_outputs.get("injection_canary")
        if (
            isinstance(canary, str)
            and canary
            and canary.casefold() in repr(_observations(outputs)).casefold()
        ):
            return _missing(key, reason="injection_canary_rejected")
        return await evaluator(outputs, reference_outputs)

    guarded.__name__ = key
    return guarded


def _missing(key: str, *, reason: str = "missing_projection") -> EvaluationResult:
    return EvaluationResult(key=key, score=None, metadata={"status": reason})


def _unavailable(key: str, error: Exception) -> EvaluationResult:
    return EvaluationResult(
        key=key,
        score=None,
        metadata={"error_type": type(error).__name__, "status": "unavailable"},
    )


async def _judge_one(
    judge: SemanticJudge,
    key: str,
    state: Mapping[str, object],
    *,
    option_order: tuple[str, ...] | None = None,
) -> JudgeDecision | EvaluationResult:
    try:
        return await judge.evaluate(key, state, option_order=option_order)
    except Exception as error:  # Provider errors become fail-closed metric coverage.
        return _unavailable(key, error)


async def _claim_supported(
    judge: SemanticJudge,
    outputs: Mapping[str, object],
    _reference: Mapping[str, object],
) -> EvaluationResult:
    raw_claims = _observations(outputs).get("claim_supported")
    if not isinstance(raw_claims, Sequence) or isinstance(raw_claims, (str, bytes, bytearray)):
        return _missing("claim_supported")
    if not raw_claims:
        return EvaluationResult(
            key="claim_supported",
            score=1.0,
            metadata={"checked_count": 0, "not_applicable": True},
        )
    decisions: list[JudgeDecision] = []
    for raw in cast("Sequence[object]", raw_claims):
        if not isinstance(raw, Mapping):
            return _missing("claim_supported", reason="invalid_projection")
        item = cast("Mapping[str, object]", raw)
        citation_ids = item.get("citation_ids")
        excerpt = item.get("excerpt")
        if (
            not isinstance(citation_ids, Sequence)
            or isinstance(citation_ids, (str, bytes, bytearray))
            or not citation_ids
            or any(not valid_citation_id(item) for item in citation_ids)
            or not isinstance(excerpt, str)
            or not excerpt.strip()
        ):
            return EvaluationResult(
                key="claim_supported",
                score=0.0,
                metadata={"status": "unresolved_citation"},
            )
        state = {field: item[field] for field in ("claim", "excerpt") if field in item}
        judged = await _judge_one(judge, "claim_supported", state)
        if isinstance(judged, EvaluationResult):
            return judged
        decisions.append(judged)
    scores = [decision.probabilities.get("yes") for decision in decisions]
    if any(not isinstance(score, (int, float)) for score in scores):
        return _missing("claim_supported", reason="invalid_result")
    return EvaluationResult(
        key="claim_supported",
        score=min(cast("list[float]", scores)),
        value=all(bool(decision.value) for decision in decisions),
        metadata={
            "checked_count": len(decisions),
            "decisions": [decision_metadata(decision) for decision in decisions],
        },
    )


async def _noul(
    judge: SemanticJudge,
    key: str,
    outputs: Mapping[str, object],
    *,
    invert: bool = False,
) -> EvaluationResult:
    state = _observations(outputs).get(key)
    if not isinstance(state, Mapping):
        return _missing(key)
    if key == "entity_resolution_ok":
        profile = state.get("resolved_profile")
        if not isinstance(profile, str) or not profile.strip():
            return EvaluationResult(key=key, score=0.0, metadata={"status": "unresolved_profile"})
    decision = await _judge_one(judge, key, cast("Mapping[str, object]", state))
    if isinstance(decision, EvaluationResult):
        return decision
    probability = decision.probabilities.get("yes")
    if not isinstance(probability, (int, float)):
        return _missing(key, reason="invalid_result")
    score = 1.0 - float(probability) if invert else float(probability)
    return EvaluationResult(
        key=key,
        score=score,
        value=decision.value,
        metadata=decision_metadata(decision),
    )


async def _next_step(
    judge: SemanticJudge,
    outputs: Mapping[str, object],
    reference: Mapping[str, object],
    option_order: tuple[str, ...],
) -> EvaluationResult:
    state = _observations(outputs).get("next_step")
    expected = reference.get("expected_next_step")
    if not isinstance(state, Mapping) or not isinstance(expected, str):
        return _missing("next_step")
    decision = await _judge_one(
        judge,
        "next_step",
        cast("Mapping[str, object]", state),
        option_order=option_order,
    )
    if isinstance(decision, EvaluationResult):
        return decision
    score = decision.probabilities.get(expected)
    if not isinstance(score, (int, float)):
        return _missing("next_step", reason="invalid_result")
    return EvaluationResult(
        key="next_step",
        score=float(score),
        value=decision.value,
        metadata={**decision_metadata(decision), "expected": expected},
    )


async def _score(
    judge: SemanticJudge,
    key: str,
    outputs: Mapping[str, object],
) -> EvaluationResult:
    state = _observations(outputs).get(key)
    if state is None and key == "tone_fit":
        return EvaluationResult(key=key, score=None, metadata={"not_applicable": True})
    if not isinstance(state, Mapping):
        return _missing(key)
    decision = await _judge_one(judge, key, cast("Mapping[str, object]", state))
    if isinstance(decision, EvaluationResult):
        return decision
    if isinstance(decision.value, bool) or not isinstance(decision.value, (int, float)):
        return _missing(key, reason="invalid_result")
    return EvaluationResult(
        key=key,
        score=float(decision.value),
        value=decision.value,
        metadata=decision_metadata(decision),
    )


def semantic_evaluators(
    judge: SemanticJudge,
    *,
    next_step_order: tuple[str, ...] | None = None,
) -> tuple[SemanticEvaluator, ...]:
    choice_order = next_step_order or QUESTIONS["next_step"].options

    async def claim(
        outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
    ) -> EvaluationResult:
        return await _claim_supported(judge, outputs, reference_outputs)

    async def leak(
        outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
    ) -> EvaluationResult:
        return await _noul(judge, "internal_data_leak", outputs, invert=True)

    async def matches(
        outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
    ) -> EvaluationResult:
        return await _noul(judge, "draft_matches_brief", outputs)

    async def next_step(
        outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
    ) -> EvaluationResult:
        return await _next_step(judge, outputs, reference_outputs, choice_order)

    async def entity(
        outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
    ) -> EvaluationResult:
        return await _noul(judge, "entity_resolution_ok", outputs)

    async def actionability(
        outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
    ) -> EvaluationResult:
        return await _score(judge, "actionability", outputs)

    async def tone(
        outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
    ) -> EvaluationResult:
        return await _score(judge, "tone_fit", outputs)

    return (
        _guard("claim_supported", claim),
        _guard("internal_data_leak", leak),
        _guard("draft_matches_brief", matches),
        _guard("next_step", next_step),
        _guard("entity_resolution_ok", entity),
        _guard("actionability", actionability),
        _guard("tone_fit", tone),
    )
