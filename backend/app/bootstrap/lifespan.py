"""FastAPI startup and shutdown resource ownership."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from time import perf_counter
from typing import cast

import structlog
from fastapi import FastAPI

from app.bootstrap.container import Container

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Validate dependencies at startup and close them on shutdown."""

    container = cast(Container, app.state.container)
    service = container.settings.service_name
    started = perf_counter()
    startup_stage = "database_readiness"
    await logger.ainfo(
        "application_starting",
        service=service,
        environment=container.settings.environment.value,
        authentication_enabled=container.auth is not None,
        prospect_enabled=container.prospect is not None,
        online_quality_enabled=container.quality is not None,
    )
    try:
        if not await container.database.ping():
            raise RuntimeError("database failed startup readiness check")
        startup_stage = "resources"
        await container.start_resources()
        container.started = True
        await logger.ainfo(
            "application_started",
            service=service,
            environment=container.settings.environment.value,
            duration_ms=round((perf_counter() - started) * 1000, 3),
        )
        yield
    except BaseException as error:
        await logger.aerror(
            "application_startup_failed" if not container.started else "application_runtime_failed",
            service=service,
            stage=startup_stage,
            error_type=type(error).__name__,
            duration_ms=round((perf_counter() - started) * 1000, 3),
        )
        raise
    finally:
        stopping = perf_counter()
        await logger.ainfo("application_stopping", service=service)
        try:
            await container.close()
        except BaseException as error:
            await logger.aerror(
                "application_shutdown_failed",
                service=service,
                error_type=type(error).__name__,
                duration_ms=round((perf_counter() - stopping) * 1000, 3),
            )
            raise
        await logger.ainfo(
            "application_stopped",
            service=service,
            duration_ms=round((perf_counter() - stopping) * 1000, 3),
        )
