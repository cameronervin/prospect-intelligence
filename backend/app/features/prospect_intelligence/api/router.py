"""Thin HTTP mapping for the injected prospect-intelligence service."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Response, status

from ..contracts.models import FitVerdict, ProspectRun, ReviewAction, SourceCoverage
from ..domain.errors import InvalidRunTransitionError, UnsafeOutreachError
from ..schemas.api import (
    AccountResponse,
    AccountsResponse,
    AccountSummary,
    BriefResponse,
    EvidenceResponse,
    LaneResponse,
    OutreachResponse,
    ProspectRunResponse,
    ReviewRunRequest,
    SourceCoverageResponse,
    StartRunRequest,
)
from ..services.runs import ProspectRunService

ScopeHeader = Annotated[
    str,
    Header(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"),
]


def build_router(
    service: ProspectRunService,
    *,
    submit_run: Callable[[UUID], None] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["prospect-intelligence"])

    @router.get("/accounts", response_model=AccountsResponse)
    def list_accounts(
        x_tenant_id: ScopeHeader,
        x_rep_id: ScopeHeader,
    ) -> AccountsResponse:
        del x_rep_id
        return AccountsResponse(
            items=[
                AccountResponse(
                    id=account.id,
                    name=account.name,
                    relationship=account.relationship,
                    industry=account.industry,
                    location=account.location,
                )
                for account in service.list_accounts(x_tenant_id)
            ]
        )

    @router.post(
        "/prospect-runs",
        response_model=ProspectRunResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def create_run(
        request: StartRunRequest,
        x_tenant_id: ScopeHeader,
        x_rep_id: ScopeHeader,
        background_tasks: BackgroundTasks,
    ) -> ProspectRunResponse:
        try:
            run = service.create_run(x_tenant_id, x_rep_id, request.account_id)
        except LookupError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
            ) from error
        response = _run_response(run)
        if submit_run is not None:
            background_tasks.add_task(submit_run, run.id)
        return response

    @router.get("/prospect-runs/{run_id}", response_model=ProspectRunResponse)
    def get_run(
        run_id: UUID,
        x_tenant_id: ScopeHeader,
        x_rep_id: ScopeHeader,
    ) -> ProspectRunResponse:
        try:
            run = service.get_scoped_run(run_id, x_tenant_id, x_rep_id)
        except LookupError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
            ) from error
        return _run_response(run)

    @router.post("/prospect-runs/{run_id}/review", response_model=ProspectRunResponse)
    def review_run(
        run_id: UUID,
        request: ReviewRunRequest,
        x_tenant_id: ScopeHeader,
        x_rep_id: ScopeHeader,
        response: Response,
    ) -> ProspectRunResponse:
        try:
            service.get_scoped_run(run_id, x_tenant_id, x_rep_id)
            run = service.review_run(
                run_id,
                ReviewAction(request.decision),
                tool_call_id=request.tool_call_id,
                edited_outreach=request.body,
            )
        except LookupError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
            ) from error
        except (InvalidRunTransitionError, UnsafeOutreachError) as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        response.status_code = status.HTTP_200_OK
        return _run_response(run)

    return router


def _run_response(run: ProspectRun) -> ProspectRunResponse:
    account = run.account
    output = run.output
    coverage: list[SourceCoverageResponse] = []
    if output is not None:
        for source in output.source_coverage:
            if isinstance(source, SourceCoverage):
                coverage.append(
                    SourceCoverageResponse(
                        source=source.source,
                        status=source.status,
                        detail=source.detail,
                    )
                )
            else:
                coverage.append(SourceCoverageResponse(source=source, status="complete"))

    brief: BriefResponse | None = None
    outreach: OutreachResponse | None = None
    verdict = None
    if output is not None:
        verdict = FitVerdict(output.verdict).value
        lanes: list[LaneResponse] = []
        for index, lane in enumerate(output.scored_lanes):
            evidence = output.lane_evidence[index] if index < len(output.lane_evidence) else ()
            lanes.append(
                LaneResponse(
                    origin=lane.origin,
                    destination=lane.destination,
                    shipper_loads_per_week=lane.shipper_loads_per_week,
                    matched_loads_per_week=lane.matched_loads_per_week,
                    fit_score=float(lane.fit_score),
                    modeled_annual_revenue=float(lane.modeled_annual_revenue),
                    deadhead_miles_avoided=lane.deadhead_miles_avoided,
                    evidence=[
                        EvidenceResponse(
                            claim=item.claim,
                            source=item.provenance.source,
                            retrieved_at=item.provenance.retrieved_at.isoformat(),
                        )
                        for item in evidence
                    ],
                )
            )
        brief = BriefResponse(
            summary=output.brief_summary or output.brief_markdown,
            recommended_next_step=output.recommended_next_step or _default_next_step(verdict),
            modeled_annual_revenue=sum(lane.modeled_annual_revenue for lane in lanes),
            deadhead_miles_avoided=sum(lane.deadhead_miles_avoided for lane in lanes),
            lanes=lanes,
        )
        body = run.reviewed_outreach or output.outreach_draft
        if body is not None and verdict == "fit":
            outreach = OutreachResponse(
                subject=output.outreach_subject or "Freight capacity conversation",
                body=body,
            )

    return ProspectRunResponse(
        id=run.id,
        account=AccountSummary(id=account.id, name=account.name),
        status=run.status.value,
        stage=run.stage,
        progress_percent=run.progress_percent,
        source_coverage=coverage,
        verdict=verdict,
        brief=brief,
        outreach=outreach,
        error=run.error,
    )


def _default_next_step(verdict: str) -> str:
    if verdict == "fit":
        return "Pitch the highest-fit lane."
    if verdict == "no_fit":
        return "Do not prioritize outreach for this account."
    return "Verify shipper lanes before outreach."
