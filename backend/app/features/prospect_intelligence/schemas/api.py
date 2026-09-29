"""Validated request and response schemas."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.features.prospect_intelligence.contracts.filesystem import SCOPE_ID_PATTERN
from app.features.prospect_intelligence.contracts.models import (
    AccountRelationship,
    FitVerdict,
    RecommendedNextStep,
    ReviewAction,
    RunStatus,
    SourceCoverageStatus,
    SourceMode,
)

ScopeId = Annotated[
    str,
    StringConstraints(min_length=3, max_length=100, pattern=SCOPE_ID_PATTERN),
]


class AccountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    relationship: AccountRelationship
    industry: str
    location: str | None


class AccountsResponse(BaseModel):
    items: list[AccountResponse]


class StartRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")


class ReviewRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReviewAction
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=10_000)
    tool_call_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")

    @model_validator(mode="after")
    def validate_edited_outreach(self) -> "ReviewRunRequest":
        has_edit = self.subject is not None or self.body is not None
        if self.decision is ReviewAction.EDIT and (not self.subject or not self.body):
            raise ValueError("subject and body are required for an edit decision")
        if self.decision is not ReviewAction.EDIT and has_edit:
            raise ValueError("subject and body are only accepted for an edit decision")
        return self


class AccountSummary(BaseModel):
    id: str
    name: str


class SourceCoverageResponse(BaseModel):
    source: str
    status: SourceCoverageStatus
    detail: str | None = None


class EvidenceResponse(BaseModel):
    claim: str
    source: str
    mode: SourceMode
    endpoint_or_artifact: str
    retrieved_at: str
    evidence_location: str
    source_version: str


class LaneResponse(BaseModel):
    origin: str
    destination: str
    shipper_loads_per_week: int
    matched_loads_per_week: int
    fit_score: float
    modeled_annual_revenue: float
    deadhead_miles_avoided: int
    evidence: list[EvidenceResponse]


class BriefResponse(BaseModel):
    summary: str
    recommended_next_step: str
    recommended_next_step_code: RecommendedNextStep
    modeled_annual_revenue: float
    deadhead_miles_avoided: int
    lanes: list[LaneResponse]


class OutreachResponse(BaseModel):
    subject: str
    body: str


class RunErrorResponse(BaseModel):
    code: str
    message: str
    retryable: bool


class PendingReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["send_outreach"]
    allowed_decisions: list[ReviewAction]
    tool_call_id: str


class ProspectRunResponse(BaseModel):
    id: UUID
    account: AccountSummary
    status: RunStatus
    stage: str
    progress_percent: int = Field(ge=0, le=100)
    source_coverage: list[SourceCoverageResponse]
    verdict: FitVerdict | None = None
    brief: BriefResponse | None = None
    outreach: OutreachResponse | None = None
    pending_review: PendingReviewResponse | None = None
    error: RunErrorResponse | None = None
