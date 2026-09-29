"""Stable HTTP error mapping."""

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Return a non-sensitive problem response for unexpected failures."""

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        await logger.aexception(
            "unhandled_request_error",
            path=request.url.path,
            error_type=type(error).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "The request could not be completed.",
                    "retryable": False,
                }
            },
        )
