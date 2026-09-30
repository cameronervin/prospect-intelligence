"""SDK-neutral contracts shared by offline targets and evaluators."""

from evaluation.contracts.judges import (
    JudgeDecision,
    JudgeProtocolError,
    SemanticJudge,
    SemanticQuestion,
    TokenPricing,
    decision_metadata,
    state_sha256,
)
from evaluation.contracts.semantic import citation_id, semantic_observations, valid_citation_id
from evaluation.contracts.semantic_states import (
    BriefDraftState,
    BriefState,
    ClaimSupportState,
    DraftState,
    EntityResolutionState,
    SemanticObservations,
    ToneFitState,
)
from evaluation.contracts.snapshot import OfflineRunSnapshot, normalize_snapshot

__all__ = [
    "BriefDraftState",
    "BriefState",
    "ClaimSupportState",
    "DraftState",
    "EntityResolutionState",
    "JudgeDecision",
    "JudgeProtocolError",
    "OfflineRunSnapshot",
    "SemanticJudge",
    "SemanticObservations",
    "SemanticQuestion",
    "TokenPricing",
    "ToneFitState",
    "citation_id",
    "decision_metadata",
    "normalize_snapshot",
    "semantic_observations",
    "state_sha256",
    "valid_citation_id",
]
