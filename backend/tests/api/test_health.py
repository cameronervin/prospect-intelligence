"""Health API tests."""

from collections.abc import Awaitable, Callable

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.platform.api.health import build_router


def app_with_readiness(readiness: Callable[[], Awaitable[bool]]) -> FastAPI:
    app = FastAPI()
    app.include_router(build_router(readiness))
    return app


@pytest.mark.asyncio
async def test_liveness_does_not_probe_database() -> None:
    calls = 0

    async def readiness() -> bool:
        nonlocal calls
        calls += 1
        raise RuntimeError("readiness should not be called")

    app = app_with_readiness(readiness)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}
    assert calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("healthy", [False, True])
async def test_readiness_reflects_injected_check(healthy: bool) -> None:
    async def readiness() -> bool:
        return healthy

    app = app_with_readiness(readiness)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == (200 if healthy else 503)
    assert response.json() == {"status": "ready" if healthy else "not_ready"}


@pytest.mark.asyncio
async def test_readiness_fails_closed_on_dependency_exception() -> None:
    async def readiness() -> bool:
        raise RuntimeError("synthetic readiness failure")

    app = app_with_readiness(readiness)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
