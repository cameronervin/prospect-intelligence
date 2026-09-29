"""Health API tests."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.bootstrap.api import create_app
from app.bootstrap.dependencies import Container
from app.platform.config.settings import Environment, Settings
from tests.fakes import FakeDatabase


def app_with_database(database: FakeDatabase, *, started: bool = True):
    settings = Settings(environment=Environment.TEST)
    container = Container(settings=settings, database=database, started=started)
    return create_app(settings, container=container)


@pytest.mark.asyncio
async def test_liveness_does_not_probe_database() -> None:
    database = FakeDatabase(raises=True)
    app = app_with_database(database)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}
    assert database.ping_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("healthy", [False, True])
async def test_readiness_reflects_database_health(healthy: bool) -> None:
    app = app_with_database(FakeDatabase(healthy=healthy))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == (200 if healthy else 503)
    assert response.json() == {"status": "ready" if healthy else "not_ready"}


@pytest.mark.asyncio
async def test_readiness_fails_closed_on_dependency_exception() -> None:
    app = app_with_database(FakeDatabase(raises=True))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
