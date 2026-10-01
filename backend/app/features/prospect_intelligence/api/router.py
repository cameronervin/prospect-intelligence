"""Thin HTTP mapping for the injected prospect-intelligence service."""

import asyncio
from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.features.authentication.public import (
    AuthenticatedUser,
    SessionUser,
    require_sales_rep,
)
from app.platform.api.errors import ErrorResponse

from ..contracts.models import OutreachDraft, ReviewAction
from ..domain.errors import InvalidRunTransitionError, UnsafeOutreachError
from ..schemas.api import (
    AccountResponse,
    AccountsResponse,
    ProspectRunResponse,
    ReviewRunRequest,
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


def build_router(
    service: ProspectRunService,
    review_handler_provider: Callable[[], ProspectAgentReviewHandler | None],
    authenticated_user: AuthenticatedUser,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        tags=["prospect-intelligence"],
        responses=ERROR_RESPONSES,
    )

    @router.get("/accounts", response_model=AccountsResponse)
    def list_accounts(
        user: Annotated[SessionUser, Depends(authenticated_user)],
    ) -> AccountsResponse:
        auth = require_sales_rep(user).auth
        return AccountsResponse(
            items=[
                AccountResponse(
                    id=account.id,
                    name=account.name,
                    relationship=account.relationship,
                    industry=account.industry,
                    location=account.location,
                )
                for account in service.list_accounts(auth)
            ]
        )

    @router.post(
        "/prospect-runs",
        response_model=ProspectRunResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def create_run(
        request: StartRunRequest,
        user: Annotated[SessionUser, Depends(authenticated_user)],
    ) -> ProspectRunResponse:
        auth = require_sales_rep(user).auth
        try:
            run = service.create_run(auth, request.account_id)
        except LookupError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
            ) from error
        response = run_response(run)
        return response

    @router.get("/prospect-runs/{run_id}", response_model=ProspectRunResponse)
    def get_run(
        run_id: UUID,
        user: Annotated[SessionUser, Depends(authenticated_user)],
    ) -> ProspectRunResponse:
        auth = require_sales_rep(user).auth
        try:
            run = service.get_scoped_run(run_id, auth)
        except LookupError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
            ) from error
        return run_response(run)

    @router.post("/prospect-runs/{run_id}/review", response_model=ProspectRunResponse)
    async def review_run(
        run_id: UUID,
        request: ReviewRunRequest,
        response: Response,
        user: Annotated[SessionUser, Depends(authenticated_user)],
    ) -> ProspectRunResponse:
        auth = require_sales_rep(user).auth
        try:
            await asyncio.to_thread(
                service.get_scoped_run,
                run_id,
                auth,
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
                auth=auth,
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
