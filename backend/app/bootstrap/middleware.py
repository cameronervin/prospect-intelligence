"""Global middleware registration."""

from collections.abc import Awaitable, Callable
from re import compile as compile_pattern
from time import perf_counter
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response

RequestHandler = Callable[[Request], Awaitable[Response]]
_CORRELATION_ID = compile_pattern(r"^[A-Za-z0-9._-]{1,64}$")
logger = structlog.get_logger(__name__)


def safe_correlation_id(candidate: str | None) -> str:
    """Accept a bounded log-safe identifier or replace it with a UUID."""

    return (
        candidate
        if candidate is not None and _CORRELATION_ID.fullmatch(candidate)
        else str(uuid4())
    )


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


def register_middleware(app: FastAPI) -> None:
    """Register correlation metadata without logging request bodies."""

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next: RequestHandler) -> Response:
        structlog.contextvars.clear_contextvars()
        correlation_id = safe_correlation_id(request.headers.get("x-correlation-id"))
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        request.state.correlation_id = correlation_id
        started = perf_counter()
        try:
            response = await call_next(request)
            response.headers["x-correlation-id"] = correlation_id
            status_code = response.status_code
            if not (request.url.path.startswith("/health/") and status_code < 500):
                fields = {
                    "method": request.method,
                    "route": _route_template(request),
                    "status_code": status_code,
                    "outcome": (
                        "success"
                        if status_code < 400
                        else "client_error"
                        if status_code < 500
                        else "server_error"
                    ),
                    "duration_ms": round((perf_counter() - started) * 1000, 3),
                }
                if status_code >= 500 and request.url.path.startswith("/health/"):
                    await logger.awarning("http_request_completed", **fields)
                elif status_code >= 500:
                    await logger.aerror("http_request_completed", **fields)
                elif status_code >= 400:
                    await logger.awarning("http_request_completed", **fields)
                else:
                    await logger.ainfo("http_request_completed", **fields)
            return response
        except Exception as error:
            await logger.aerror(
                "http_request_failed",
                method=request.method,
                route=_route_template(request),
                error_type=type(error).__name__,
                duration_ms=round((perf_counter() - started) * 1000, 3),
            )
            raise
        finally:
            structlog.contextvars.clear_contextvars()
