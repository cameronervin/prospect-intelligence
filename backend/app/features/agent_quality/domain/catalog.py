"""Provider-neutral catalog of application quality evaluators."""

from dataclasses import dataclass
from enum import StrEnum

EVALUATOR_VERSION = "freight-evaluators-v3"


class EvaluationScope(StrEnum):
    """The LangChain evaluation scope consumed by an evaluator."""

    SINGLE_STEP = "single_step"
    TRAJECTORY = "trajectory"
    FINAL_OUTPUT = "final_output"


class EvaluationKind(StrEnum):
    """Whether a metric is computed locally or by a semantic judge."""

    DETERMINISTIC = "deterministic"
    SEMANTIC = "semantic"


@dataclass(frozen=True, slots=True)
class EvaluatorDefinition:
    key: str
    scope: EvaluationScope
    kind: EvaluationKind


def _definition(
    key: str,
    scope: EvaluationScope,
    kind: EvaluationKind = EvaluationKind.DETERMINISTIC,
) -> EvaluatorDefinition:
    return EvaluatorDefinition(key=key, scope=scope, kind=kind)


EVALUATOR_CATALOG: tuple[EvaluatorDefinition, ...] = (
    _definition("numeric_groundedness", EvaluationScope.FINAL_OUTPUT),
    _definition("lane_precision_at_3", EvaluationScope.FINAL_OUTPUT),
    _definition("analysis_correctness", EvaluationScope.FINAL_OUTPUT),
    _definition("fit_verdict_accuracy", EvaluationScope.FINAL_OUTPUT),
    _definition("file_contract", EvaluationScope.FINAL_OUTPUT),
    _definition("trajectory_checks", EvaluationScope.TRAJECTORY),
    _definition("injection_resistance", EvaluationScope.TRAJECTORY),
    _definition("latency_seconds", EvaluationScope.TRAJECTORY),
    _definition("cost_usd", EvaluationScope.TRAJECTORY),
    _definition("tool_call_count", EvaluationScope.TRAJECTORY),
    _definition("claim_supported", EvaluationScope.FINAL_OUTPUT, EvaluationKind.SEMANTIC),
    _definition("internal_data_leak", EvaluationScope.FINAL_OUTPUT, EvaluationKind.SEMANTIC),
    _definition("draft_matches_brief", EvaluationScope.FINAL_OUTPUT, EvaluationKind.SEMANTIC),
    _definition("next_step", EvaluationScope.FINAL_OUTPUT, EvaluationKind.SEMANTIC),
    _definition("entity_resolution_ok", EvaluationScope.SINGLE_STEP, EvaluationKind.SEMANTIC),
    _definition("actionability", EvaluationScope.FINAL_OUTPUT, EvaluationKind.SEMANTIC),
    _definition("tone_fit", EvaluationScope.FINAL_OUTPUT, EvaluationKind.SEMANTIC),
)
DETERMINISTIC_EVALUATOR_KEYS: tuple[str, ...] = tuple(
    definition.key
    for definition in EVALUATOR_CATALOG
    if definition.kind is EvaluationKind.DETERMINISTIC
)
SEMANTIC_EVALUATOR_KEYS: tuple[str, ...] = tuple(
    definition.key for definition in EVALUATOR_CATALOG if definition.kind is EvaluationKind.SEMANTIC
)

_DEFINITIONS_BY_KEY = {definition.key: definition for definition in EVALUATOR_CATALOG}
if len(_DEFINITIONS_BY_KEY) != len(EVALUATOR_CATALOG):
    raise RuntimeError("evaluator catalog keys must be unique")


def evaluator_definition(key: str) -> EvaluatorDefinition:
    """Return the canonical definition for a metric key."""

    try:
        return _DEFINITIONS_BY_KEY[key]
    except KeyError as error:
        raise KeyError(f"unknown evaluator key: {key}") from error
