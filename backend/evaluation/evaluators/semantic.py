"""LangSmith-native adapters for the injected semantic judges."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import cast

from langsmith.evaluation import EvaluationResult

from app.features.agent_quality import public as agent_quality
from app.features.agent_quality.contracts.models import QualitySignal
from app.features.agent_quality.domain.semantic_scoring import score_semantic_decisions
from evaluation.contracts.judges import JudgeDecision, SemanticJudge
from evaluation.contracts.semantic import valid_citation_id
from evaluation.rubrics import QUESTIONS

type SemanticEvaluator = Callable[
    [Mapping[str, object], Mapping[str, object]], Awaitable[EvaluationResult]
]
SEMANTIC_EVALUATOR_KEYS = agent_quality.SEMANTIC_EVALUATOR_KEYS


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


def _result(signal: QualitySignal) -> EvaluationResult:
    return EvaluationResult(
        key=signal.key,
        score=signal.score,
        value=signal.value,
        metadata=dict(signal.metadata),
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
        return _result(score_semantic_decisions("claim_supported", (), not_applicable=True))
    decisions: list[JudgeDecision] = []
    for raw in cast("Sequence[object]", raw_claims):
        if not isinstance(raw, Mapping):
            return _missing("claim_supported", reason="invalid_projection")
        item = cast("Mapping[str, object]", raw)
        citation_ids = item.get("citation_ids")
        excerpt = item.get("excerpt")
        typed_citation_ids = (
            cast("Sequence[object]", citation_ids)
            if isinstance(citation_ids, Sequence)
            and not isinstance(citation_ids, (str, bytes, bytearray))
            else ()
        )
        if (
            not typed_citation_ids
            or any(not valid_citation_id(identifier) for identifier in typed_citation_ids)
            or not isinstance(excerpt, str)
            or not excerpt.strip()
        ):
            return _result(score_semantic_decisions("claim_supported", (), unresolved=True))
        state = {field: item[field] for field in ("claim", "excerpt") if field in item}
        judged = await _judge_one(judge, "claim_supported", state)
        if isinstance(judged, EvaluationResult):
            return judged
        decisions.append(judged)
    try:
        return _result(score_semantic_decisions("claim_supported", decisions))
    except ValueError:
        return _missing("claim_supported", reason="invalid_result")


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
    typed_state = cast("Mapping[str, object]", state)
    if key == "entity_resolution_ok":
        profile = typed_state.get("resolved_profile")
        if not isinstance(profile, str) or not profile.strip():
            return _result(score_semantic_decisions(key, (), unresolved=True))
    decision = await _judge_one(judge, key, typed_state)
    if isinstance(decision, EvaluationResult):
        return decision
    try:
        signal = score_semantic_decisions(key, (decision,))
    except ValueError:
        return _missing(key, reason="invalid_result")
    if invert != (key == "internal_data_leak"):
        raise ValueError("semantic noul inversion does not match its catalog key")
    return _result(signal)


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
    try:
        signal = score_semantic_decisions("next_step", (decision,), expected_value=expected)
    except ValueError:
        return _missing("next_step", reason="invalid_result")
    return _result(signal)


async def _score(
    judge: SemanticJudge,
    key: str,
    outputs: Mapping[str, object],
) -> EvaluationResult:
    state = _observations(outputs).get(key)
    if state is None and key == "tone_fit":
        return _result(score_semantic_decisions(key, (), not_applicable=True))
    if not isinstance(state, Mapping):
        return _missing(key)
    decision = await _judge_one(judge, key, cast("Mapping[str, object]", state))
    if isinstance(decision, EvaluationResult):
        return decision
    try:
        signal = score_semantic_decisions(key, (decision,))
    except ValueError:
        return _missing(key, reason="invalid_result")
    return _result(signal)


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
