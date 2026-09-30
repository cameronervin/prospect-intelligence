"""Runtime composition helpers for bounded semantic judge states."""

from collections.abc import Mapping
from typing import cast

from app.features.agent_quality.contracts.semantic_judges import project_state
from app.features.agent_quality.contracts.semantic_states import SemanticObservations
from app.features.agent_quality.domain.semantic_rubrics import QUESTIONS

type SemanticStateItem = tuple[str, Mapping[str, object]]


def _item(key: str, state: object) -> SemanticStateItem:
    projected = project_state(QUESTIONS[key], cast("Mapping[str, object]", state))
    return key, projected


def semantic_state_items(observations: SemanticObservations) -> tuple[SemanticStateItem, ...]:
    """Return rubric-ordered states, expanding claims and omitting unavailable tone state."""

    items = [_item("claim_supported", state) for state in observations["claim_supported"]]
    items.extend(
        (
            _item("internal_data_leak", observations["internal_data_leak"]),
            _item("draft_matches_brief", observations["draft_matches_brief"]),
            _item("next_step", observations["next_step"]),
            _item("entity_resolution_ok", observations["entity_resolution_ok"]),
            _item("actionability", observations["actionability"]),
        )
    )
    tone_state = observations["tone_fit"]
    if tone_state is not None:
        items.append(_item("tone_fit", tone_state))
    return tuple(items)
