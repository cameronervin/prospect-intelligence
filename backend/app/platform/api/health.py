"""Application liveness and injected readiness endpoints."""

from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Stable health response contract."""

    status: Literal["live", "ready", "not_ready"]


def build_router(readiness: Callable[[], Awaitable[bool]]) -> APIRouter:
    """Build health routes around an application-owned readiness check."""

    router = APIRouter(prefix="/health", tags=["health"])

    @router.get("/live", response_model=HealthResponse)
    async def live() -> HealthResponse:
        return HealthResponse(status="live")

    @router.get("/ready", response_model=HealthResponse)
    async def ready() -> HealthResponse | JSONResponse:
        try:
            is_ready = await readiness()
        except Exception:
            is_ready = False
        if is_ready:
            return HealthResponse(status="ready")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=HealthResponse(status="not_ready").model_dump(),
            headers={"cache-control": "no-store"},
        )

    return router
