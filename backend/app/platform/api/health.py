"""Application liveness and readiness endpoints."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.bootstrap.dependencies import Container

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    """Stable health response contract."""

    status: Literal["live", "ready", "not_ready"]


def get_container(request: Request) -> Container:
    """Resolve the application container from FastAPI state."""

    return cast(Container, request.app.state.container)


ContainerDependency = Annotated[Container, Depends(get_container)]


@router.get("/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    """Report process liveness without checking dependencies."""

    return HealthResponse(status="live")


@router.get("/ready", response_model=HealthResponse)
async def ready(container: ContainerDependency) -> HealthResponse | JSONResponse:
    """Report readiness after checking the database dependency."""

    if await container.is_ready():
        return HealthResponse(status="ready")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=HealthResponse(status="not_ready").model_dump(),
        headers={"cache-control": "no-store"},
    )
