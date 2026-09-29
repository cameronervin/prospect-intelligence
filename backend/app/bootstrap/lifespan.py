"""FastAPI startup and shutdown resource ownership."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

import structlog
from fastapi import FastAPI

from app.bootstrap.dependencies import Container

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Validate dependencies at startup and close them on shutdown."""

    container = cast(Container, app.state.container)
    try:
        if not await container.database.ping():
            raise RuntimeError("database failed startup readiness check")
        await container.start_resources()
        container.started = True
        await logger.ainfo(
            "application_started",
            service=container.settings.service_name,
            environment=container.settings.environment.value,
        )
        yield
    finally:
        await container.close()
        await logger.ainfo("application_stopped", service=container.settings.service_name)
