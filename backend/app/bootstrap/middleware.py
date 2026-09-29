"""Global middleware registration."""

from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request, Response

RequestHandler = Callable[[Request], Awaitable[Response]]


def register_middleware(app: FastAPI) -> None:
    """Register correlation metadata without logging request bodies."""

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next: RequestHandler) -> Response:
        correlation_id = request.headers.get("x-correlation-id") or str(uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["x-correlation-id"] = correlation_id
        return response
