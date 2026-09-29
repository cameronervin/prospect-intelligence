"""Typed cross-layer and cross-feature contracts."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from ..domain.models import LaneFitResult


class SourceMode(StrEnum):
    LIVE = "live"
    FIXTURE = "fixture"
    SNAPSHOT = "snapshot"


@dataclass(frozen=True, slots=True)
class Provenance:
    """Required lineage carried by every sourced fact."""

    source: str
    mode: SourceMode
    endpoint_or_artifact: str
    retrieved_at: datetime
    evidence_location: str
    source_version: str


@dataclass(frozen=True, slots=True)
class Evidence:
    claim: str
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class Account:
    id: str
    tenant_id: str
    name: str
    relationship: Literal["Prospect", "Customer"]
    industry: str
    location: str | None = None


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


class FitVerdict(StrEnum):
    FIT = "fit"
    NO_FIT = "no_fit"
    NEEDS_MORE_DATA = "needs_more_data"


class ReviewAction(StrEnum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"


class QualityEventType(StrEnum):
    RUN_CREATED = "run_created"
    ANALYSIS_COMPLETED = "analysis_completed"
    REVIEW_COMPLETED = "review_completed"
    RUN_FAILED = "run_failed"


@dataclass(frozen=True, slots=True)
class SourceCoverage:
    source: str
    status: Literal["complete", "degraded", "unavailable"]
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class AnalysisOutput:
    verdict: FitVerdict | str
    brief_markdown: str
    outreach_draft: str | None
    scored_lanes: tuple[LaneFitResult, ...]
    source_coverage: tuple[SourceCoverage | str, ...]
    brief_summary: str | None = None
    recommended_next_step: str | None = None
    outreach_subject: str | None = None
    lane_evidence: tuple[tuple[Evidence, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class ProspectRun:
    id: UUID
    tenant_id: str
    rep_id: str
    account: Account
    status: RunStatus
    stage: str
    progress_percent: int
    created_at: datetime
    updated_at: datetime
    output: AnalysisOutput | None = None
    reviewed_outreach: str | None = None
    review_action: ReviewAction | None = None
    send_receipt_id: UUID | None = None
    error: str | None = None
    quality_metadata: dict[str, str] = field(default_factory=lambda: dict[str, str]())


@dataclass(frozen=True, slots=True)
class SendReceipt:
    id: UUID
    run_id: UUID
    tool_call_id: str
    simulated: bool
    sent_at: datetime
    outreach: str


@dataclass(frozen=True, slots=True)
class RepPreference:
    tenant_id: str
    rep_id: str
    summary: str
    learned_at: datetime


@dataclass(frozen=True, slots=True)
class QualityEvent:
    """Sanitized event safe for online quality processing.

    Raw tenant/rep identifiers, prompts, drafts, contacts, credentials, provider payloads,
    and model outputs are deliberately absent from this cross-feature contract.
    """

    event_id: UUID
    run_id: UUID
    account_id: str
    tenant_id_hash: str
    rep_id_hash: str
    event_type: QualityEventType
    occurred_at: datetime
    agent_version: str
    prompt_version: str
    verdict: FitVerdict | None = None
    review_decision: ReviewAction | None = None
    edit_distance: float | None = None
    source_modes: tuple[SourceMode, ...] = ()
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.edit_distance is not None and not 0 <= self.edit_distance <= 1:
            raise ValueError("edit distance must be between 0 and 1")
        if len(self.tenant_id_hash) < 16 or len(self.rep_id_hash) < 16:
            raise ValueError("quality events require hashed tenant and rep identifiers")

    def to_payload(self) -> dict[str, object]:
        """Serialize only the explicit sanitized allowlist."""

        return {
            "event_id": str(self.event_id),
            "run_id": str(self.run_id),
            "account_id": self.account_id,
            "tenant_id_hash": self.tenant_id_hash,
            "rep_id_hash": self.rep_id_hash,
            "event_type": self.event_type.value,
            "occurred_at": self.occurred_at.isoformat(),
            "agent_version": self.agent_version,
            "prompt_version": self.prompt_version,
            "verdict": self.verdict.value if self.verdict is not None else None,
            "review_decision": (
                self.review_decision.value if self.review_decision is not None else None
            ),
            "edit_distance": self.edit_distance,
            "source_modes": [mode.value for mode in self.source_modes],
            "error_code": self.error_code,
        }
