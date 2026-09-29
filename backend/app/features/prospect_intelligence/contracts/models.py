"""Typed cross-layer and cross-feature contracts."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from ..domain.models import LaneFitResult


class SourceMode(StrEnum):
    LIVE = "live"
    FIXTURE = "fixture"
    SNAPSHOT = "snapshot"


class AccountRelationship(StrEnum):
    PROSPECT = "Prospect"
    CUSTOMER = "Customer"


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
    relationship: AccountRelationship
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


class RecommendedNextStep(StrEnum):
    EXPAND_EXISTING_LANES = "expand_existing_lanes"
    NEW_LANE_PITCH = "new_lane_pitch"
    NOT_A_FIT = "not_a_fit"
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


class SourceCoverageStatus(StrEnum):
    COMPLETE = "complete"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class SourceCoverage:
    source: str
    status: SourceCoverageStatus
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ScoredLane:
    score: LaneFitResult
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True, slots=True)
class ProspectBrief:
    summary: str
    markdown: str
    recommended_next_step: RecommendedNextStep
    recommendation: str
    lanes: tuple[ScoredLane, ...]


@dataclass(frozen=True, slots=True)
class OutreachDraft:
    subject: str
    body: str


@dataclass(frozen=True, slots=True)
class AnalysisOutput:
    verdict: FitVerdict
    brief: ProspectBrief
    outreach: OutreachDraft | None
    source_coverage: tuple[SourceCoverage, ...]


@dataclass(frozen=True, slots=True)
class RunError:
    code: str
    message: str
    retryable: bool


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
    reviewed_outreach: OutreachDraft | None = None
    review_action: ReviewAction | None = None
    send_receipt_id: UUID | None = None
    error: RunError | None = None
    quality_metadata: dict[str, str] = field(default_factory=lambda: dict[str, str]())


@dataclass(frozen=True, slots=True)
class SendReceipt:
    id: UUID
    run_id: UUID
    tool_call_id: str
    simulated: bool
    sent_at: datetime
    outreach: OutreachDraft


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
        sha256_hex = re.compile(r"^[0-9a-f]{64}$")
        if not sha256_hex.fullmatch(self.tenant_id_hash) or not sha256_hex.fullmatch(
            self.rep_id_hash
        ):
            raise ValueError("quality events require lowercase SHA-256 tenant and rep hashes")

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
