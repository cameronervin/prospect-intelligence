"""FastAPI application factory and ASGI entrypoint."""

from fastapi import FastAPI

from app.bootstrap.container import Container
from app.bootstrap.exception_handlers import register_exception_handlers
from app.bootstrap.lifespan import lifespan
from app.bootstrap.middleware import register_middleware
from app.bootstrap.wiring import build_container
from app.features.authentication.public import (
    build_authenticated_user,
)
from app.features.authentication.public import (
    build_router as build_auth_router,
)
from app.features.prospect_intelligence.api.router import build_router as build_prospect_router
from app.platform.api.health import build_router as build_health_router
from app.platform.config.settings import Settings
from app.platform.observability.logging import configure_logging
from app.platform.observability.tracing import configure_trace_privacy


def create_app(
    settings: Settings | None = None,
    *,
    container: Container | None = None,
) -> FastAPI:
    """Create an application with injectable settings and dependencies."""

    configure_trace_privacy()
    resolved_settings = settings or Settings()
    configure_logging(level=resolved_settings.log_level, json_output=resolved_settings.log_json)
    docs_url = "/docs" if resolved_settings.docs_enabled else None
    openapi_url = "/openapi.json" if resolved_settings.docs_enabled else None
    app = FastAPI(
        title="LangChain Take-Home API",
        version="0.1.0",
        docs_url=docs_url,
        redoc_url=None,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )
    resolved_container = container or build_container(resolved_settings)
    app.state.container = resolved_container
    register_exception_handlers(app)
    register_middleware(app)
    app.include_router(build_health_router(resolved_container.is_ready))
    authenticated_user = None
    if resolved_container.auth is not None:
        authenticated_user = build_authenticated_user(resolved_container.auth)
        app.include_router(build_auth_router(resolved_container.auth, authenticated_user))
    if resolved_container.prospect is not None:
        if authenticated_user is None:
            raise RuntimeError("prospect routes require authentication")
        component = resolved_container.prospect
        app.include_router(
            build_prospect_router(
                component.service,
                lambda: component.review_handler,
                authenticated_user,
            )
        )
    return app
