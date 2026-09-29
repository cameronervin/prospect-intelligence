"""Thin HTTP mapping for the injected prospect-intelligence service."""

import asyncio
from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Response, status

from app.platform.api.errors import ErrorResponse

from ..contracts.models import FitVerdict, OutreachDraft, ProspectRun, ReviewAction
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
    RunErrorResponse,
    ScopeId,
    SourceCoverageResponse,
    StartRunRequest,
)
from ..services.agent_reviews import ProspectAgentReviewHandler
from ..services.runs import ProspectRunService

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}
TenantHeader = Annotated[ScopeId, Header(alias="X-Tenant-Id")]
RepHeader = Annotated[ScopeId, Header(alias="X-Rep-Id")]


def build_router(
    service: ProspectRunService,
    review_handler_provider: Callable[[], ProspectAgentReviewHandler | None],
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        tags=["prospect-intelligence"],
        responses=ERROR_RESPONSES,
    )

    @router.get("/accounts", response_model=AccountsResponse)
    def list_accounts(
        x_tenant_id: TenantHeader,
        x_rep_id: RepHeader,
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
        x_tenant_id: TenantHeader,
        x_rep_id: RepHeader,
    ) -> ProspectRunResponse:
        try:
            run = service.create_run(x_tenant_id, x_rep_id, request.account_id)
        except LookupError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
            ) from error
        response = _run_response(run)
        return response

    @router.get("/prospect-runs/{run_id}", response_model=ProspectRunResponse)
    def get_run(
        run_id: UUID,
        x_tenant_id: TenantHeader,
        x_rep_id: RepHeader,
    ) -> ProspectRunResponse:
        try:
            run = service.get_scoped_run(run_id, x_tenant_id, x_rep_id)
        except LookupError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
            ) from error
        return _run_response(run)

    @router.post("/prospect-runs/{run_id}/review", response_model=ProspectRunResponse)
    async def review_run(
        run_id: UUID,
        request: ReviewRunRequest,
        x_tenant_id: TenantHeader,
        x_rep_id: RepHeader,
        response: Response,
    ) -> ProspectRunResponse:
        try:
            await asyncio.to_thread(
                service.get_scoped_run,
                run_id,
                x_tenant_id,
                x_rep_id,
            )
            edited_outreach = (
                OutreachDraft(subject=request.subject, body=request.body)
                if request.decision is ReviewAction.EDIT
                and request.subject is not None
                and request.body is not None
                else None
            )
            review_handler = review_handler_provider()
            if review_handler is None:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Prospect review is temporarily unavailable",
                )
            run = await review_handler(
                run_id,
                request.decision,
                tool_call_id=request.tool_call_id,
                edited_outreach=edited_outreach,
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
    coverage = (
        [
            SourceCoverageResponse(
                source=source.source,
                status=source.status,
                detail=source.detail,
            )
            for source in output.source_coverage
        ]
        if output is not None
        else []
    )

    brief: BriefResponse | None = None
    outreach: OutreachResponse | None = None
    verdict = None
    if output is not None:
        verdict = output.verdict
        lanes: list[LaneResponse] = []
        for scored_lane in output.brief.lanes:
            lane = scored_lane.score
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
                            mode=item.provenance.mode,
                            endpoint_or_artifact=item.provenance.endpoint_or_artifact,
                            retrieved_at=item.provenance.retrieved_at.isoformat(),
                            evidence_location=item.provenance.evidence_location,
                            source_version=item.provenance.source_version,
                        )
                        for item in scored_lane.evidence
                    ],
                )
            )
        brief = BriefResponse(
            summary=output.brief.summary,
            recommended_next_step=output.brief.recommendation,
            recommended_next_step_code=output.brief.recommended_next_step,
            modeled_annual_revenue=sum(lane.modeled_annual_revenue for lane in lanes),
            deadhead_miles_avoided=sum(lane.deadhead_miles_avoided for lane in lanes),
            lanes=lanes,
        )
        reviewed_outreach = run.reviewed_outreach or output.outreach
        if reviewed_outreach is not None and verdict is FitVerdict.FIT:
            outreach = OutreachResponse(
                subject=reviewed_outreach.subject,
                body=reviewed_outreach.body,
            )

    return ProspectRunResponse(
        id=run.id,
        account=AccountSummary(id=account.id, name=account.name),
        status=run.status,
        stage=run.stage,
        progress_percent=run.progress_percent,
        source_coverage=coverage,
        verdict=verdict,
        brief=brief,
        outreach=outreach,
        error=(
            RunErrorResponse(
                code=run.error.code,
                message=run.error.message,
                retryable=run.error.retryable,
            )
            if run.error is not None
            else None
        ),
    )
