"""Application lifecycle tests."""

import pytest

from app.bootstrap.api import create_app
from app.bootstrap.dependencies import Container
from app.platform.config.settings import Environment, Settings
from tests.fakes import FakeDatabase


@pytest.mark.asyncio
async def test_lifespan_marks_ready_and_closes_dependencies() -> None:
    settings = Settings(environment=Environment.TEST)
    database = FakeDatabase()
    container = Container(settings=settings, database=database)
    app = create_app(settings, container=container)

    async with app.router.lifespan_context(app):
        assert container.started is True
        assert await container.is_ready() is True

    assert container.started is False
    assert database.closed is True


@pytest.mark.asyncio
async def test_lifespan_fails_closed_when_database_is_unavailable() -> None:
    settings = Settings(environment=Environment.TEST)
    database = FakeDatabase(healthy=False)
    container = Container(settings=settings, database=database)
    app = create_app(settings, container=container)

    with pytest.raises(RuntimeError, match="database failed startup readiness check"):
        async with app.router.lifespan_context(app):
            pass

    assert container.started is False
