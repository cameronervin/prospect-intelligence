"""Shared provider-neutral scoring for offline and online semantic decisions."""

from collections.abc import Sequence

from app.features.agent_quality.contracts.models import QualitySignal
from app.features.agent_quality.contracts.semantic_judges import (
    JudgeDecision,
    decision_metadata,
)


def score_semantic_decisions(
    key: str,
    decisions: Sequence[JudgeDecision],
    *,
    expected_value: str | None = None,
    not_applicable: bool = False,
    unresolved: bool = False,
) -> QualitySignal:
    """Normalize one criterion without retaining judge state or raw output."""

    if not_applicable:
        return QualitySignal(
            key=key,
            score=1.0 if key == "claim_supported" else None,
            passed=None,
            value=True if key == "claim_supported" else None,
            metadata={
                **({"checked_count": 0} if key == "claim_supported" else {}),
                "not_applicable": True,
            },
        )
    if unresolved:
        status = "unresolved_citation" if key == "claim_supported" else "unresolved_profile"
        return QualitySignal(
            key=key,
            score=0.0,
            passed=False,
            value=False,
            metadata={"status": status},
        )
    if not decisions:
        raise ValueError(f"semantic evaluator has no decisions: {key}")
    if key == "claim_supported":
        probabilities = [_yes_probability(decision) for decision in decisions]
        return QualitySignal(
            key=key,
            score=min(probabilities),
            passed=None,
            value=all(bool(decision.value) for decision in decisions),
            metadata={
                **decision_metadata(decisions[0]),
                "checked_count": len(decisions),
                "instance_count": len(decisions),
                "decisions": [decision_metadata(decision) for decision in decisions],
            },
        )
    decision = decisions[0]
    metadata = decision_metadata(decision)
    metadata["instance_count"] = len(decisions)
    if key == "internal_data_leak":
        score = 1.0 - _yes_probability(decision)
    elif key in {"draft_matches_brief", "entity_resolution_ok"}:
        score = _yes_probability(decision)
    elif key == "next_step":
        if expected_value is None:
            raise ValueError("next_step semantic scoring requires an expected value")
        probability = decision.probabilities.get(expected_value)
        if isinstance(probability, bool) or not isinstance(probability, int | float):
            raise ValueError("next_step semantic evaluator omitted expected probability")
        score = float(probability)
        metadata["expected"] = expected_value
    elif key in {"actionability", "tone_fit"}:
        if isinstance(decision.value, bool) or not isinstance(decision.value, int | float):
            raise ValueError(f"semantic evaluator returned a non-numeric score: {key}")
        return QualitySignal(
            key=key,
            score=float(decision.value),
            passed=None,
            value=float(decision.value),
            scale_min=1.0,
            scale_max=5.0,
            metadata=metadata,
        )
    else:
        raise ValueError(f"unknown semantic evaluator: {key}")
    return QualitySignal(
        key=key,
        score=score,
        passed=None,
        value=decision.value,
        metadata=metadata,
    )


def _yes_probability(decision: JudgeDecision) -> float:
    value = decision.probabilities.get("yes")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("semantic evaluator omitted yes probability")
    return float(value)
