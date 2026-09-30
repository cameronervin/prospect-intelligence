"""Thin HTTP mapping for the injected prospect-intelligence service."""

import asyncio
from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Response, status

from app.platform.api.errors import ErrorResponse

from ..contracts.models import OutreachDraft, ReviewAction
from ..domain.errors import InvalidRunTransitionError, UnsafeOutreachError
from ..schemas.api import (
    AccountResponse,
    AccountsResponse,
    ProspectRunResponse,
    ReviewRunRequest,
    ScopeId,
    StartRunRequest,
)
from ..services.agent_reviews import ProspectAgentReviewHandler
from ..services.runs import ProspectRunService
from .serializers import run_response

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
        response = run_response(run)
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
        return run_response(run)

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
        return run_response(run)

    return router
