"""Typed minimal states exposed to semantic evaluators."""

from typing import TypedDict


class ClaimSupportState(TypedDict):
    claim: str
    excerpt: str
    citation_ids: list[str]


class DraftState(TypedDict):
    draft: str


class BriefDraftState(TypedDict):
    brief: str
    draft: str


class BriefState(TypedDict):
    brief: str


class EntityResolutionState(TypedDict):
    account_name: str
    resolved_profile: str


class ToneFitState(TypedDict):
    draft: str
    rep_preferences: str


class SemanticObservations(TypedDict):
    claim_supported: list[ClaimSupportState]
    internal_data_leak: DraftState | None
    draft_matches_brief: BriefDraftState | None
    next_step: BriefState
    entity_resolution_ok: EntityResolutionState
    actionability: BriefState
    tone_fit: ToneFitState | None
