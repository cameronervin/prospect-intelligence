"""Stable HTTP error mapping."""

from collections.abc import Mapping

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.platform.api.errors import (
    ApiErrorCode,
    ErrorDetail,
    ErrorIssue,
    ErrorResponse,
)

logger = structlog.get_logger(__name__)
_AUTH_PATH = "/api/v1/auth"
_AUTH_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}


def register_exception_handlers(app: FastAPI) -> None:
    """Return one non-sensitive error envelope for request failures."""

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        issues = [
            ErrorIssue(
                location=".".join(str(part) for part in item["loc"]),
                message=str(item["msg"]),
                type=str(item["type"]),
            )
            for item in error.errors()
        ]
        return _response(
            422,
            ErrorDetail(
                code=ApiErrorCode.VALIDATION_ERROR,
                message="Request validation failed.",
                retryable=False,
                issues=issues,
            ),
            headers=_error_headers(request),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = {
            401: ApiErrorCode.UNAUTHORIZED,
            403: ApiErrorCode.FORBIDDEN,
            404: ApiErrorCode.NOT_FOUND,
            409: ApiErrorCode.CONFLICT,
            503: ApiErrorCode.SERVICE_UNAVAILABLE,
        }.get(error.status_code, ApiErrorCode.INTERNAL_ERROR)
        return _response(
            error.status_code,
            ErrorDetail(
                code=code,
                message=error.detail,
                retryable=error.status_code == 503,
            ),
            headers=_error_headers(request, error.headers),
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        route = request.scope.get("route")
        route_template = getattr(route, "path", None)
        await logger.aerror(
            "unhandled_request_error",
            route=route_template if isinstance(route_template, str) else "unmatched",
            error_type=type(error).__name__,
        )
        return _response(
            500,
            ErrorDetail(
                code=ApiErrorCode.INTERNAL_ERROR,
                message="The request could not be completed.",
                retryable=False,
            ),
            headers=_error_headers(request),
        )


def _response(
    status_code: int,
    detail: ErrorDetail,
    *,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=detail).model_dump(mode="json"),
        headers=headers,
    )


def _error_headers(
    request: Request,
    headers: Mapping[str, str] | None = None,
) -> Mapping[str, str] | None:
    merged = dict(headers or {})
    path = request.url.path
    if path == _AUTH_PATH or path.startswith(f"{_AUTH_PATH}/"):
        merged.update(_AUTH_NO_CACHE_HEADERS)
    return merged or None
