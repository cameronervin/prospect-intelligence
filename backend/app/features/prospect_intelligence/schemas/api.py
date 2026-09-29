"""Validated request and response schemas."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AccountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    relationship: Literal["Prospect", "Customer"]
    industry: str
    location: str | None


class AccountsResponse(BaseModel):
    items: list[AccountResponse]


class StartRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")


class ReviewRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "edit", "reject"]
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=10_000)
    tool_call_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")


class AccountSummary(BaseModel):
    id: str
    name: str


class SourceCoverageResponse(BaseModel):
    source: str
    status: Literal["complete", "degraded", "unavailable"]
    detail: str | None = None


class EvidenceResponse(BaseModel):
    claim: str
    source: str
    retrieved_at: str


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
    modeled_annual_revenue: float
    deadhead_miles_avoided: int
    lanes: list[LaneResponse]


class OutreachResponse(BaseModel):
    subject: str
    body: str


class ProspectRunResponse(BaseModel):
    id: UUID
    account: AccountSummary
    status: Literal["queued", "running", "awaiting_review", "completed", "rejected", "failed"]
    stage: str
    progress_percent: int = Field(ge=0, le=100)
    source_coverage: list[SourceCoverageResponse]
    verdict: Literal["fit", "no_fit", "needs_more_data"] | None = None
    brief: BriefResponse | None = None
    outreach: OutreachResponse | None = None
    error: str | None = None
